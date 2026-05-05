"""Test that ingest applies auto-detection suggestions onto pages.

Locks in: blank/color/normal pages get the right suggested page_type after
ingest, and the median aspect of the source images is recorded as the
project's default `page_h_w_ratio` override.
"""

from __future__ import annotations

import io
import zipfile
from datetime import UTC, datetime

import numpy as np
import pytest

from pd_prep_for_pgdp.adapters.database.sqlite import SqliteDatabase
from pd_prep_for_pgdp.adapters.storage.filesystem import FilesystemStorage
from pd_prep_for_pgdp.core.models import (
    PageType,
    PipelineState,
    Project,
    ProjectConfig,
    ProjectStatus,
)


def _png_blank() -> bytes:
    cv2 = pytest.importorskip("cv2")
    img = np.full((1000, 800, 3), 252, dtype=np.uint8)
    ok, buf = cv2.imencode(".png", img)
    assert ok
    return bytes(buf.tobytes())


def _png_text() -> bytes:
    cv2 = pytest.importorskip("cv2")
    h, w = 1000, 800
    img = np.full((h, w, 3), 250, dtype=np.uint8)
    cv2.rectangle(img, (80, 80), (w - 80, h - 80), (0, 0, 0), -1)
    ok, buf = cv2.imencode(".png", img)
    assert ok
    return bytes(buf.tobytes())


def _png_color() -> bytes:
    cv2 = pytest.importorskip("cv2")
    h, w = 1000, 800
    img = np.zeros((h, w, 3), dtype=np.uint8)
    img[:, : w // 3] = (255, 0, 0)
    img[:, w // 3 : 2 * w // 3] = (0, 255, 0)
    img[:, 2 * w // 3 :] = (0, 0, 255)
    ok, buf = cv2.imencode(".png", img)
    assert ok
    return bytes(buf.tobytes())


def _make_zip(entries: list[tuple[str, bytes]]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for n, d in entries:
            zf.writestr(n, d)
    return buf.getvalue()


def _project(project_id: str = "p1") -> Project:
    now = datetime.now(UTC)
    return Project(
        id=project_id,
        owner_id="default",
        name="t",
        created_at=now,
        updated_at=now,
        status=ProjectStatus.ingesting,
        page_count=0,
        proof_page_count=0,
        config=ProjectConfig(book_name="t", source_uri=""),
        pipeline_state=PipelineState(),
        storage_prefix=f"projects/{project_id}/",
    )


@pytest.fixture
async def db(tmp_path) -> SqliteDatabase:
    d = SqliteDatabase(f"sqlite:///{(tmp_path / 's.db').as_posix()}")
    await d.initialize()
    return d


@pytest.fixture
def storage(tmp_path) -> FilesystemStorage:
    return FilesystemStorage(root=tmp_path / "data")


@pytest.mark.asyncio
async def test_ingest_writes_auto_detect_suggestions(
    db: SqliteDatabase, storage: FilesystemStorage
) -> None:
    pytest.importorskip("cv2")
    from pd_prep_for_pgdp.core.ingest import ingest_source

    project = _project()
    await db.put_project(project)
    zip_bytes = _make_zip(
        [
            ("p1.png", _png_text()),
            ("p2.png", _png_blank()),
            ("p3.png", _png_color()),
        ]
    )
    src_key = f"projects/{project.id}/source.zip"
    await storage.put_bytes(src_key, zip_bytes)

    await ingest_source(
        project=project,
        source_type="zip",
        source_key=src_key,
        storage=storage,
        database=db,
        auto_detect=True,
    )

    pages, _, _ = await db.list_pages(project.id, None, 100)
    by_stem = {p.source_stem: p for p in pages}
    assert by_stem["p1"].page_type == PageType.normal
    assert by_stem["p2"].page_type == PageType.blank
    assert by_stem["p3"].page_type == PageType.plate_p


@pytest.mark.asyncio
async def test_ingest_records_median_aspect_in_default_overrides(
    db: SqliteDatabase, storage: FilesystemStorage
) -> None:
    pytest.importorskip("cv2")
    from pd_prep_for_pgdp.core.ingest import ingest_source

    project = _project()
    await db.put_project(project)
    # Three pages all at aspect 1.65 -> median 1.65.
    zip_bytes = _make_zip([("p.png", _png_text())] * 3)
    await storage.put_bytes(f"projects/{project.id}/source.zip", zip_bytes)

    await ingest_source(
        project=project,
        source_type="zip",
        source_key=f"projects/{project.id}/source.zip",
        storage=storage,
        database=db,
        auto_detect=True,
    )

    refreshed = await db.get_project(project.id)
    assert refreshed is not None
    # page_h_w_ratio is recorded in default_overrides for the project.
    assert "page_h_w_ratio" in refreshed.config.default_overrides
    assert abs(float(refreshed.config.default_overrides["page_h_w_ratio"]) - 1.25) < 0.5


@pytest.mark.asyncio
async def test_ingest_skips_auto_detect_when_disabled(
    db: SqliteDatabase, storage: FilesystemStorage
) -> None:
    pytest.importorskip("cv2")
    from pd_prep_for_pgdp.core.ingest import ingest_source

    project = _project()
    await db.put_project(project)
    zip_bytes = _make_zip([("p1.png", _png_blank())])
    await storage.put_bytes(f"projects/{project.id}/source.zip", zip_bytes)

    await ingest_source(
        project=project,
        source_type="zip",
        source_key=f"projects/{project.id}/source.zip",
        storage=storage,
        database=db,
        auto_detect=False,
    )

    pages, _, _ = await db.list_pages(project.id, None, 100)
    # No suggestions applied — page_type stays at the model default.
    assert pages[0].page_type == PageType.normal
