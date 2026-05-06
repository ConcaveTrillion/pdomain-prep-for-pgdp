"""Cover `_run_batch_pages` and `_handle_extract_illustrations` branches.

Locks in:
  - Running a batch_process_pages handler without a GPU backend wired
    raises a clear RuntimeError naming the missing dependency.
  - Empty batch (no proof-range pages, no requested page_idxs) is a clean
    "nothing to do" — no error, progress.message reads "no pages to process".
  - extract_illustrations skips pages whose source_key is missing on
    storage and records each as a per-page error rather than failing the
    whole job.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from pd_prep_for_pgdp.adapters.database.sqlite import SqliteDatabase
from pd_prep_for_pgdp.adapters.storage.filesystem import FilesystemStorage
from pd_prep_for_pgdp.core.job_runner import (
    InProcessJobRunner,
    _handle_extract_illustrations,
    _run_batch_pages,
)
from pd_prep_for_pgdp.core.models import (
    IllustrationRegion,
    Job,
    JobStatus,
    JobType,
    PageRecord,
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


def _project(project_id: str = "p1") -> Project:
    now = datetime.now(UTC)
    return Project(
        id=project_id,
        owner_id="default",
        name="t",
        created_at=now,
        updated_at=now,
        status=ProjectStatus.processing,
        page_count=0,
        proof_page_count=0,
        config=ProjectConfig(book_name="t", source_uri=""),
        pipeline_state=PipelineState(),
        storage_prefix=f"projects/{project_id}/",
    )


@pytest.mark.asyncio
async def test_batch_pages_missing_project_raises(db, storage) -> None:
    """The handler raises FileNotFoundError when the project is gone — the
    runner wraps it as JobStatus.error like every other handler."""
    from pd_prep_for_pgdp.adapters.gpu.cpu import CpuBackend

    runner = InProcessJobRunner(database=db, storage=storage, gpu=CpuBackend(storage=storage, database=db))
    job = Job(
        id="j-noproj",
        project_id="ghost",
        owner_id="default",
        type=JobType.batch_process_pages,
        status=JobStatus.queued,
    )
    await db.put_job(job)
    with pytest.raises(FileNotFoundError, match="ghost"):
        await _run_batch_pages(runner, job, job_type="batch_process_pages")


@pytest.mark.asyncio
async def test_batch_pages_requires_gpu_backend(db, storage) -> None:
    """No gpu= argument → RuntimeError naming the requirement."""
    runner = InProcessJobRunner(database=db, storage=storage, gpu=None)
    await db.put_project(_project())
    job = Job(
        id="j",
        project_id="p1",
        owner_id="default",
        type=JobType.batch_process_pages,
        status=JobStatus.queued,
    )
    await db.put_job(job)
    with pytest.raises(RuntimeError, match="requires a GPU backend"):
        await _run_batch_pages(runner, job, job_type="batch_process_pages")


@pytest.mark.asyncio
async def test_batch_pages_empty_no_op(db, storage, monkeypatch) -> None:
    """Project has no pages → handler records 'no pages to process' progress
    and returns without dispatching anything."""
    from pd_prep_for_pgdp.adapters.gpu.cpu import CpuBackend

    runner = InProcessJobRunner(database=db, storage=storage, gpu=CpuBackend(storage=storage, database=db))
    await db.put_project(_project())  # No pages added.
    job = Job(
        id="j-empty",
        project_id="p1",
        owner_id="default",
        type=JobType.batch_process_pages,
        status=JobStatus.queued,
    )
    await db.put_job(job)

    await _run_batch_pages(runner, job, job_type="batch_process_pages")

    refreshed = await db.get_job("j-empty")
    assert refreshed is not None
    assert refreshed.progress.total == 0
    assert "no pages" in refreshed.progress.message


@pytest.mark.asyncio
async def test_extract_illustrations_records_missing_source_per_page(db, storage) -> None:
    runner = InProcessJobRunner(database=db, storage=storage)
    project = _project()
    await db.put_project(project)
    # Page 0: has regions but source_key references a key not in storage.
    # Page 1: has no regions — should be skipped silently (the `continue` branch).
    page_with_regions = PageRecord(
        project_id=project.id,
        idx0=0,
        prefix="p001",
        source_stem="src1",
        source_key=f"projects/{project.id}/source/src1.png",  # not uploaded
        illustration_regions=[
            IllustrationRegion(index=1, L=0, R=10, T=0, B=10, output_format="jpg"),
        ],
    )
    page_no_regions = PageRecord(
        project_id=project.id,
        idx0=1,
        prefix="p002",
        source_stem="src2",
    )
    await db.put_pages([page_with_regions, page_no_regions])
    job = Job(
        id="j-ill",
        project_id=project.id,
        owner_id="default",
        type=JobType.batch_extract_illustrations,
        status=JobStatus.queued,
    )
    await db.put_job(job)

    await _handle_extract_illustrations(runner, job)

    refreshed = await db.get_job("j-ill")
    assert refreshed is not None
    # Total extracted is 0 (the only candidate had a missing source).
    assert refreshed.progress.current == 0
    # The progress message records that there were errors.
    assert "1 errors" in refreshed.progress.message or "errors" in refreshed.progress.message
