"""Lock in CpuBackend.run_batch error / unknown-type handling.

`run_batch` is the dispatch entry point local + self-hosted modes use to
process pages. Locks in:
  - unknown `job_type` → BatchJobResult(ok=False, error="unsupported …"),
  - per-item failures (e.g. project missing) don't abort the batch — each
    item gets its own error result and the rest still run,
  - `batch_process_pages` requires storage+database wiring; the backend
    raises a clear RuntimeError when those weren't injected.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from pd_prep_for_pgdp.adapters.database.sqlite import SqliteDatabase
from pd_prep_for_pgdp.adapters.gpu.base import BatchJobItem
from pd_prep_for_pgdp.adapters.gpu.cpu import CpuBackend
from pd_prep_for_pgdp.adapters.storage.filesystem import FilesystemStorage
from pd_prep_for_pgdp.core.models import (
    PipelineState,
    Project,
    ProjectConfig,
    ProjectStatus,
)


@pytest.fixture
async def db(tmp_path) -> SqliteDatabase:
    d = SqliteDatabase(f"sqlite:///{(tmp_path / 's.db').as_posix()}")
    await d.initialize()
    return d


@pytest.fixture
def storage(tmp_path) -> FilesystemStorage:
    return FilesystemStorage(root=tmp_path / "data")


def _project() -> Project:
    now = datetime.now(UTC)
    return Project(
        id="p1",
        owner_id="default",
        name="t",
        created_at=now,
        updated_at=now,
        status=ProjectStatus.processing,
        page_count=0,
        proof_page_count=0,
        config=ProjectConfig(book_name="t", source_uri=""),
        pipeline_state=PipelineState(),
        storage_prefix="projects/p1/",
    )


@pytest.mark.asyncio
async def test_run_batch_marks_unknown_job_type_as_error(
    db: SqliteDatabase, storage: FilesystemStorage
) -> None:
    backend = CpuBackend(storage=storage, database=db)
    item = BatchJobItem(job_type="not_a_real_type", project_id="p1", idx0=0, payload={})

    results = await backend.run_batch([item])

    assert len(results) == 1
    r = results[0]
    assert r.ok is False
    assert r.error and "unsupported" in r.error
    assert r.job_type == "not_a_real_type"


@pytest.mark.asyncio
async def test_run_batch_isolates_failure_per_item(db: SqliteDatabase, storage: FilesystemStorage) -> None:
    """First item fails (project missing); second succeeds (unknown type)."""
    backend = CpuBackend(storage=storage, database=db)
    items = [
        # project doesn't exist -> process_page raises FileNotFoundError ->
        # caught and returned as ok=False.
        BatchJobItem(job_type="batch_process_pages", project_id="missing-project", idx0=0, payload={}),
        # Unknown job type — should land in the explicit "unsupported" branch
        # and NOT be aborted by the previous failure.
        BatchJobItem(job_type="zzz", project_id="p1", idx0=1, payload={}),
    ]

    results = await backend.run_batch(items)

    assert len(results) == 2
    assert results[0].ok is False
    assert results[0].idx0 == 0
    assert results[1].ok is False
    assert results[1].idx0 == 1
    assert "unsupported" in (results[1].error or "")


@pytest.mark.asyncio
async def test_process_page_requires_storage_and_database() -> None:
    """A backend instantiated without storage/db is unusable for routes."""
    from pd_prep_for_pgdp.adapters.gpu.base import ProcessPageRequest
    from pd_prep_for_pgdp.core.models import PageConfigOverrides

    backend = CpuBackend()  # no storage, no database
    with pytest.raises(RuntimeError, match="requires storage \\+ database"):
        await backend.process_page(
            ProcessPageRequest(
                project_id="p1",
                idx0=0,
                config_overrides=PageConfigOverrides(),
                output_context="commit",
            )
        )


@pytest.mark.asyncio
async def test_run_ocr_requires_storage_and_database() -> None:
    from pd_prep_for_pgdp.adapters.gpu.base import OcrPageRequest

    backend = CpuBackend()
    with pytest.raises(RuntimeError, match="requires storage \\+ database"):
        await backend.run_ocr(OcrPageRequest(project_id="p1", idx0=0))
