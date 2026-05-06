"""Lock in the words-blob persistence path (P1 #6 — TextReviewPage overlay).

`CpuBackend.run_ocr` writes the OCR text at `<root>.txt`. As of this
iteration it ALSO writes a sibling `<root>.words.json` containing the
serialised `list[OcrWord]` so the text-review overlay has bboxes to
render on a fresh page mount (without re-running OCR).

This file locks in:
  - the words-blob lands at the expected sibling key,
  - its on-disk shape round-trips through `OcrWord` validation,
  - whole-page (no split_suffix) and per-split keys both work,
  - `words_key_for` derives the sibling key correctly.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from pd_prep_for_pgdp.adapters.database.sqlite import SqliteDatabase
from pd_prep_for_pgdp.adapters.gpu.base import OcrPageRequest
from pd_prep_for_pgdp.adapters.gpu.cpu import (
    CpuBackend,
    load_words_from_storage,
    words_key_for,
)
from pd_prep_for_pgdp.adapters.storage.filesystem import FilesystemStorage
from pd_prep_for_pgdp.core.models import (
    BoundingBox,
    OcrWord,
    PageRecord,
    PipelineState,
    Project,
    ProjectConfig,
    ProjectStatus,
)


def test_words_key_for_replaces_txt_suffix() -> None:
    assert words_key_for("projects/p1/ocr_text/src1_p001.txt") == "projects/p1/ocr_text/src1_p001.words.json"


def test_words_key_for_handles_missing_txt_suffix_defensively() -> None:
    # Defensive: should never happen in practice, but don't crash.
    assert words_key_for("projects/p1/ocr_text/weird") == "projects/p1/ocr_text/weird.words.json"


def test_load_words_from_storage_round_trips() -> None:
    words = [
        OcrWord(
            id="w1",
            text="hello",
            confidence=0.99,
            bounding_box=BoundingBox(left=10, top=20, width=30, height=40),
        ),
        OcrWord(
            id="w2",
            text="world",
            confidence=0.5,
            bounding_box=BoundingBox(left=50, top=60, width=70, height=80),
            split_suffix="L",
        ),
    ]
    blob = json.dumps([w.model_dump(mode="json") for w in words]).encode("utf-8")
    decoded = load_words_from_storage(blob)
    assert decoded == words


# ─── End-to-end: run_ocr writes the words blob ──────────────────────────────


@pytest.fixture
async def db(tmp_path: Path) -> SqliteDatabase:
    d = SqliteDatabase(f"sqlite:///{(tmp_path / 's.db').as_posix()}")
    await d.initialize()
    return d


@pytest.fixture
def storage(tmp_path: Path) -> FilesystemStorage:
    return FilesystemStorage(root=tmp_path / "data")


async def _seed_project_and_page(
    db: SqliteDatabase,
    *,
    project_id: str = "wp1",
    idx0: int = 0,
    prefix: str = "p001",
    source_stem: str = "src1",
) -> None:
    now = datetime.now(UTC)
    await db.put_project(
        Project(
            id=project_id,
            owner_id="default",
            name="t",
            created_at=now,
            updated_at=now,
            status=ProjectStatus.processing,
            page_count=1,
            proof_page_count=1,
            config=ProjectConfig(book_name="t", source_uri=""),
            pipeline_state=PipelineState(),
            storage_prefix=f"projects/{project_id}/",
        )
    )
    await db.put_pages([PageRecord(project_id=project_id, idx0=idx0, prefix=prefix, source_stem=source_stem)])


async def _seed_ocr_image(
    storage: FilesystemStorage,
    *,
    project_id: str,
    source_stem: str,
    full_prefix: str,
) -> None:
    """Drop a fake PNG at the OCR-cropped key so run_ocr's `exists()` check passes."""
    key = f"projects/{project_id}/ocr_images/{source_stem}_{full_prefix}.png"
    # Content irrelevant — _ocr_image_bytes is monkeypatched.
    await storage.put_bytes(key, b"\x89PNG\r\n\x1a\n", "image/png")


@pytest.mark.asyncio
async def test_run_ocr_persists_words_blob_alongside_text(
    db: SqliteDatabase, storage: FilesystemStorage, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Whole-page (no split_suffix) → text + words blob land side-by-side."""
    await _seed_project_and_page(db)
    await _seed_ocr_image(storage, project_id="wp1", source_stem="src1", full_prefix="p001")

    sample_words = [
        OcrWord(
            id="w-a",
            text="lorem",
            confidence=0.95,
            bounding_box=BoundingBox(left=1, top=2, width=10, height=20),
        ),
        OcrWord(
            id="w-b",
            text="ipsum",
            confidence=0.88,
            bounding_box=BoundingBox(left=11, top=2, width=12, height=20),
        ),
    ]

    def fake_ocr_image_bytes(
        img_bytes: bytes, cfg: Any, system: Any, split_suffix: str | None
    ) -> tuple[str, list[OcrWord]]:
        return "lorem ipsum", list(sample_words)

    monkeypatch.setattr("pd_prep_for_pgdp.adapters.gpu.cpu._ocr_image_bytes", fake_ocr_image_bytes)

    backend = CpuBackend(storage=storage, database=db)
    resp = await backend.run_ocr(OcrPageRequest(project_id="wp1", idx0=0))

    assert resp.text == "lorem ipsum"
    assert resp.text_key == "projects/wp1/ocr_text/src1_p001.txt"

    # Text blob landed.
    assert await storage.exists(resp.text_key)
    # Sibling words blob landed.
    expected_words_key = "projects/wp1/ocr_text/src1_p001.words.json"
    assert await storage.exists(expected_words_key)

    # On-disk shape round-trips through OcrWord validation.
    raw = await storage.get_bytes(expected_words_key)
    decoded = load_words_from_storage(raw)
    assert decoded == sample_words


@pytest.mark.asyncio
async def test_run_ocr_persists_words_blob_for_split_page(
    db: SqliteDatabase, storage: FilesystemStorage, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Per-split (split_suffix='L') → words blob keyed at <stem>_<prefix>L.words.json."""
    await _seed_project_and_page(db, project_id="wp2")
    await _seed_ocr_image(storage, project_id="wp2", source_stem="src1", full_prefix="p001L")

    sample_words = [
        OcrWord(
            id="w-1",
            text="left",
            confidence=0.9,
            bounding_box=BoundingBox(left=5, top=5, width=10, height=10),
            split_suffix="L",
        )
    ]

    def fake_ocr_image_bytes(
        img_bytes: bytes, cfg: Any, system: Any, split_suffix: str | None
    ) -> tuple[str, list[OcrWord]]:
        # Mirror the real helper: stamp split_suffix onto each word.
        words = [w.model_copy(update={"split_suffix": split_suffix}) for w in sample_words]
        return "left", words

    monkeypatch.setattr("pd_prep_for_pgdp.adapters.gpu.cpu._ocr_image_bytes", fake_ocr_image_bytes)

    backend = CpuBackend(storage=storage, database=db)
    resp = await backend.run_ocr(OcrPageRequest(project_id="wp2", idx0=0, split_suffix="L"))

    assert resp.text_key == "projects/wp2/ocr_text/src1_p001L.txt"
    expected_words_key = "projects/wp2/ocr_text/src1_p001L.words.json"
    assert await storage.exists(expected_words_key)

    decoded = load_words_from_storage(await storage.get_bytes(expected_words_key))
    assert len(decoded) == 1
    assert decoded[0].split_suffix == "L"


@pytest.mark.asyncio
async def test_run_ocr_persists_empty_words_list_when_no_words(
    db: SqliteDatabase, storage: FilesystemStorage, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A page with zero recognised words still gets a (valid, empty) words blob."""
    await _seed_project_and_page(db, project_id="wp3")
    await _seed_ocr_image(storage, project_id="wp3", source_stem="src1", full_prefix="p001")

    def fake_ocr_image_bytes(
        img_bytes: bytes, cfg: Any, system: Any, split_suffix: str | None
    ) -> tuple[str, list[OcrWord]]:
        return "", []

    monkeypatch.setattr("pd_prep_for_pgdp.adapters.gpu.cpu._ocr_image_bytes", fake_ocr_image_bytes)

    backend = CpuBackend(storage=storage, database=db)
    resp = await backend.run_ocr(OcrPageRequest(project_id="wp3", idx0=0))

    expected_words_key = words_key_for(resp.text_key)
    assert await storage.exists(expected_words_key)
    decoded = load_words_from_storage(await storage.get_bytes(expected_words_key))
    assert decoded == []
