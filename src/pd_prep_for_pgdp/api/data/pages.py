"""/api/data/projects/{id}/pages/* — page CRUD."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from ...adapters.auth import UserContext
from ...adapters.database import IDatabase
from ...adapters.gpu.cpu import load_words_from_storage, words_key_for
from ...adapters.storage import IStorage
from ...core.models import (
    AlignmentOverride,
    IllustrationRegion,
    OcrWord,
    PageConfigOverrides,
    PageProcessingStatus,
    PageRecord,
    PageSplit,
    PageType,
)
from ..dependencies import get_database, get_storage, get_user

log = logging.getLogger(__name__)

router = APIRouter(tags=["pages"])


class ListPagesResponse(BaseModel):
    pages: list[PageRecord]
    next_cursor: str | None = None
    total: int


class UpdatePageRequest(BaseModel):
    page_type: PageType | None = None
    alignment: AlignmentOverride | None = None
    config_overrides: PageConfigOverrides | None = None
    splits: list[PageSplit] | None = None
    illustration_regions: list[IllustrationRegion] | None = None


class UpdatePageTextRequest(BaseModel):
    split_suffix: str | None = None
    text: str


class UpdatePageTextResponse(BaseModel):
    text_key: str


class GetPageTextResponse(BaseModel):
    text: str
    text_key: str
    # Bboxes for the TextReviewPage overlay. Empty list for legacy pages
    # OCR'd before the words blob was written (or for pages whose words
    # file was lost). The frontend treats `[]` and "no overlay" as the
    # same case, so empty-list is the more idiomatic shape than None.
    words: list[OcrWord] = []


@router.get(
    "/projects/{project_id}/pages",
    response_model=ListPagesResponse,
)
async def list_pages(
    project_id: str,
    cursor: str | None = Query(None),
    limit: int = Query(50, ge=1, le=500),
    page_type: PageType | None = Query(None),
    has_splits: bool | None = Query(None),
    status: PageProcessingStatus | None = Query(None),
    review_needed: bool | None = Query(None),
    user: UserContext = Depends(get_user),
    db: IDatabase = Depends(get_database),
) -> ListPagesResponse:
    project = await db.get_project(project_id)
    if project is None or project.owner_id != user.user_id:
        raise HTTPException(404, "project not found")

    pages, next_cursor, total = await db.list_pages(project_id, cursor, limit)
    if page_type is not None:
        pages = [p for p in pages if p.page_type == page_type]
    if has_splits is not None:
        pages = [p for p in pages if bool(p.splits) == has_splits]
    if status is not None:
        pages = [p for p in pages if p.processing_status == status]
    if review_needed is True:
        pages = [p for p in pages if _needs_review(p)]
    if review_needed is False:
        pages = [p for p in pages if not _needs_review(p)]
    # When the caller filters, total reflects the visible page count so the
    # UI can render "N of M pages need review".
    filtered_total = (
        len(pages) if any(f is not None for f in (page_type, has_splits, status, review_needed)) else total
    )
    return ListPagesResponse(pages=pages, next_cursor=next_cursor, total=filtered_total)


def _needs_review(page: PageRecord) -> bool:
    """Spec 03 review-queue heuristic: any output not complete, or has an error."""
    if page.processing_status == PageProcessingStatus.error:
        return True
    if not page.outputs:
        # Pre-OCR pages don't need review yet.
        return False
    for o in page.outputs:
        if o.ocr_status != PageProcessingStatus.complete:
            return True
        if o.ocr_error:
            return True
    return False


@router.get(
    "/projects/{project_id}/pages/{idx0}",
    response_model=PageRecord,
)
async def get_page(
    project_id: str,
    idx0: int,
    user: UserContext = Depends(get_user),
    db: IDatabase = Depends(get_database),
) -> PageRecord:
    project = await db.get_project(project_id)
    if project is None or project.owner_id != user.user_id:
        raise HTTPException(404, "project not found")
    page = await db.get_page(project_id, idx0)
    if page is None:
        raise HTTPException(404, "page not found")
    return page


@router.patch(
    "/projects/{project_id}/pages/{idx0}",
    response_model=PageRecord,
)
async def update_page(
    project_id: str,
    idx0: int,
    body: UpdatePageRequest,
    user: UserContext = Depends(get_user),
    db: IDatabase = Depends(get_database),
) -> PageRecord:
    project = await db.get_project(project_id)
    if project is None or project.owner_id != user.user_id:
        raise HTTPException(404, "project not found")
    page = await db.get_page(project_id, idx0)
    if page is None:
        raise HTTPException(404, "page not found")
    update = body.model_dump(exclude_unset=True)
    if "config_overrides" in update and update["config_overrides"] is not None:
        page.config_overrides = PageConfigOverrides.model_validate(update["config_overrides"])
    if "page_type" in update:
        page.page_type = body.page_type or page.page_type
    if "alignment" in update:
        page.alignment = body.alignment or page.alignment
    if "splits" in update and body.splits is not None:
        page.splits = body.splits
    if "illustration_regions" in update and body.illustration_regions is not None:
        page.illustration_regions = body.illustration_regions
    await db.put_page(page)
    return page


@router.patch(
    "/projects/{project_id}/pages/{idx0}/text",
    response_model=UpdatePageTextResponse,
)
async def update_page_text(
    project_id: str,
    idx0: int,
    body: UpdatePageTextRequest,
    user: UserContext = Depends(get_user),
    db: IDatabase = Depends(get_database),
    storage: IStorage = Depends(get_storage),
) -> UpdatePageTextResponse:
    project = await db.get_project(project_id)
    if project is None or project.owner_id != user.user_id:
        raise HTTPException(404, "project not found")
    page = await db.get_page(project_id, idx0)
    if page is None:
        raise HTTPException(404, "page not found")

    # Step 9 must write to the same key the OCR step wrote to, so the package
    # stage picks up the edits. Prefer the recorded `output.ocr_text_key` when
    # available; fall back to the synthesised path for pre-OCR edits.
    suffix = body.split_suffix or ""
    text_key: str | None = None
    for output in page.outputs:
        if (output.split_suffix or "") == suffix and output.ocr_text_key:
            text_key = output.ocr_text_key
            break
    if text_key is None:
        full_prefix = f"{page.prefix}{suffix}"
        stem_prefix = f"{page.source_stem}_{full_prefix}" if page.source_stem else full_prefix
        text_key = f"projects/{project_id}/ocr_text/{stem_prefix}.txt"
    await storage.put_bytes(text_key, body.text.encode("utf-8"), "text/plain")
    return UpdatePageTextResponse(text_key=text_key)


@router.get(
    "/projects/{project_id}/pages/{idx0}/text/{suffix}",
    response_model=GetPageTextResponse,
)
async def get_page_text(
    project_id: str,
    idx0: int,
    suffix: str,
    user: UserContext = Depends(get_user),
    db: IDatabase = Depends(get_database),
    storage: IStorage = Depends(get_storage),
) -> GetPageTextResponse:
    project = await db.get_project(project_id)
    if project is None or project.owner_id != user.user_id:
        raise HTTPException(404, "project not found")
    page = await db.get_page(project_id, idx0)
    if page is None:
        raise HTTPException(404, "page not found")
    real_suffix = "" if suffix == "_" else suffix
    text_key: str | None = None
    for output in page.outputs:
        if (output.split_suffix or "") == real_suffix and output.ocr_text_key:
            text_key = output.ocr_text_key
            break
    if text_key is None:
        full_prefix = f"{page.prefix}{real_suffix}"
        stem_prefix = f"{page.source_stem}_{full_prefix}" if page.source_stem else full_prefix
        text_key = f"projects/{project_id}/ocr_text/{stem_prefix}.txt"
    if not await storage.exists(text_key):
        raise HTTPException(404, "text not found")
    text = (await storage.get_bytes(text_key)).decode("utf-8")

    # Try to load the sibling words blob. Legacy pages OCR'd before
    # `cpu.run_ocr` started persisting words won't have one — return [].
    words: list[OcrWord] = []
    words_key = words_key_for(text_key)
    if await storage.exists(words_key):
        try:
            raw = await storage.get_bytes(words_key)
            words = load_words_from_storage(raw)
        except Exception:
            log.exception("failed to decode words blob at %s; returning empty list", words_key)
            words = []

    return GetPageTextResponse(text=text, text_key=text_key, words=words)
