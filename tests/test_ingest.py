"""Tests-first for `core.ingest`.

Locks in:
  - zip extraction populates `source/` keys in storage,
  - one PageRecord per source image, sorted, idx0 starts at 0,
  - thumbnails are generated under `thumbnails/`,
  - project status becomes `configuring` after ingest completes,
  - corrupt zip entries are skipped (errors recorded but ingest continues),
  - `s3_folder`/`local_folder` source types use list_prefix instead of unzipping.
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
    PageProcessingStatus,
    PipelineState,
    Project,
    ProjectConfig,
    ProjectStatus,
)


def _png(h: int, w: int, fill: int = 200) -> bytes:
    cv2 = pytest.importorskip("cv2")
    img = np.full((h, w, 3), fill, dtype=np.uint8)
    ok, buf = cv2.imencode(".png", img)
    assert ok
    return bytes(buf.tobytes())


def _make_zip(entries: list[tuple[str, bytes]]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, data in entries:
            zf.writestr(name, data)
    return buf.getvalue()


def _project(project_id: str = "p1") -> Project:
    now = datetime.now(UTC)
    return Project(
        id=project_id,
        owner_id="default",
        name="Test Book",
        created_at=now,
        updated_at=now,
        status=ProjectStatus.ingesting,
        page_count=0,
        proof_page_count=0,
        config=ProjectConfig(book_name="test-book", source_uri=""),
        pipeline_state=PipelineState(),
        storage_prefix=f"projects/{project_id}/",
    )


@pytest.fixture
async def db(tmp_path) -> SqliteDatabase:
    d = SqliteDatabase(f"sqlite:///{(tmp_path / 'state.db').as_posix()}")
    await d.initialize()
    return d


@pytest.fixture
def storage(tmp_path) -> FilesystemStorage:
    return FilesystemStorage(root=tmp_path / "data")


@pytest.mark.asyncio
async def test_ingest_zip_creates_one_page_per_image(
    db: SqliteDatabase, storage: FilesystemStorage
) -> None:
    from pd_prep_for_pgdp.core.ingest import ingest_source

    project = _project()
    await db.put_project(project)

    zip_bytes = _make_zip(
        [
            ("page_002.png", _png(100, 80)),
            ("page_001.png", _png(100, 80)),
            ("page_003.png", _png(100, 80)),
        ]
    )
    source_key = f"projects/{project.id}/source.zip"
    await storage.put_bytes(source_key, zip_bytes)

    result = await ingest_source(
        project=project,
        source_type="zip",
        source_key=source_key,
        storage=storage,
        database=db,
    )

    assert result.page_count == 3
    assert result.errors == []

    pages, _, total = await db.list_pages(project.id, None, 100)
    assert total == 3
    # Sorted by source filename, idx0 contiguous.
    assert [p.idx0 for p in pages] == [0, 1, 2]
    assert [p.source_stem for p in pages] == ["page_001", "page_002", "page_003"]
    # Each page references its source key.
    for p in pages:
        assert p.source_key and await storage.exists(p.source_key)
        assert p.thumbnail_key and await storage.exists(p.thumbnail_key)
        assert p.processing_status == PageProcessingStatus.pending


@pytest.mark.asyncio
async def test_ingest_zip_advances_project_status(
    db: SqliteDatabase, storage: FilesystemStorage
) -> None:
    from pd_prep_for_pgdp.core.ingest import ingest_source

    project = _project()
    await db.put_project(project)
    zip_bytes = _make_zip([("p.png", _png(50, 50))])
    await storage.put_bytes(f"projects/{project.id}/source.zip", zip_bytes)

    await ingest_source(
        project=project,
        source_type="zip",
        source_key=f"projects/{project.id}/source.zip",
        storage=storage,
        database=db,
    )

    refreshed = await db.get_project(project.id)
    assert refreshed is not None
    assert refreshed.status == ProjectStatus.configuring
    assert refreshed.page_count == 1


@pytest.mark.asyncio
async def test_ingest_zip_skips_non_image_entries(
    db: SqliteDatabase, storage: FilesystemStorage
) -> None:
    from pd_prep_for_pgdp.core.ingest import ingest_source

    project = _project()
    await db.put_project(project)
    zip_bytes = _make_zip(
        [
            ("README.txt", b"not an image"),
            ("dir/page_1.png", _png(50, 50)),
            ("dir/page_2.jpg", _png(50, 50)),
        ]
    )
    await storage.put_bytes(f"projects/{project.id}/source.zip", zip_bytes)

    result = await ingest_source(
        project=project,
        source_type="zip",
        source_key=f"projects/{project.id}/source.zip",
        storage=storage,
        database=db,
    )

    assert result.page_count == 2  # png + jpg, README skipped


@pytest.mark.asyncio
async def test_ingest_zip_records_corrupt_entries_as_errors(
    db: SqliteDatabase, storage: FilesystemStorage
) -> None:
    from pd_prep_for_pgdp.core.ingest import ingest_source

    project = _project()
    await db.put_project(project)
    zip_bytes = _make_zip(
        [
            ("page_1.png", _png(50, 50)),
            ("page_2.png", b"not actually a png"),  # cv2.imdecode -> None
        ]
    )
    await storage.put_bytes(f"projects/{project.id}/source.zip", zip_bytes)

    result = await ingest_source(
        project=project,
        source_type="zip",
        source_key=f"projects/{project.id}/source.zip",
        storage=storage,
        database=db,
    )

    # Healthy page is ingested; corrupt one is recorded as an error.
    assert result.page_count == 1
    assert any("page_2" in e for e in result.errors)


@pytest.mark.asyncio
async def test_ingest_local_folder_lists_storage_prefix(
    db: SqliteDatabase, storage: FilesystemStorage
) -> None:
    from pd_prep_for_pgdp.core.ingest import ingest_source

    project = _project()
    await db.put_project(project)
    folder_prefix = f"projects/{project.id}/raw/"
    await storage.put_bytes(f"{folder_prefix}page_a.png", _png(40, 40))
    await storage.put_bytes(f"{folder_prefix}page_b.png", _png(40, 40))

    result = await ingest_source(
        project=project,
        source_type="local_folder",
        source_key=folder_prefix,
        storage=storage,
        database=db,
    )

    assert result.page_count == 2
