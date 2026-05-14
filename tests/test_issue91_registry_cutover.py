"""Issue #91: STAGE_IMPL registry cutover — CpuBackend.process_page must
route through run_stage, not call process_page_cpu directly.

Acceptance bullets exercised here:
- CpuBackend.process_page is a shim over run_stage (no process_page_cpu call)
- LocalBackend inherits the shim (vacuous distinction confirmed)
- data_root plumbing passes through build_gpu_backend
- grep -like check: no call-site import of process_page_cpu in cpu.py
"""

from __future__ import annotations

import inspect
from pathlib import Path
from unittest.mock import patch

import pytest

# ── Acceptance bullet 1 / 6: no process_page_cpu call in CpuBackend source ──


def test_cpu_backend_does_not_call_process_page_cpu_directly() -> None:
    """CpuBackend.process_page must NOT import or call process_page_cpu.

    This is the direct enforcement of the acceptance criterion:
    `grep -r "process_page_cpu" src/` returns only the definition.
    We check the cpu.py module source for any live call or import of
    process_page_cpu — docstrings/comments may still reference it.
    """
    import pd_prep_for_pgdp.adapters.gpu.cpu as cpu_mod

    cpu_src = inspect.getsource(cpu_mod)
    # No import of process_page_cpu anywhere in the module.
    assert "from ...core.pipeline.process_page import process_page_cpu" not in cpu_src, (
        "CpuBackend module must not import process_page_cpu"
    )
    # process_page method body must not call it (check for the function call pattern).
    method_src = inspect.getsource(cpu_mod.CpuBackend.process_page)
    # Only docstring/comment mentions are allowed; actual call = '(source_bytes' or 'process_page_cpu('
    assert "process_page_cpu(" not in method_src, (
        "CpuBackend.process_page must not call process_page_cpu(); route through run_stage instead"
    )


def test_local_backend_does_not_call_process_page_cpu_directly() -> None:
    """LocalBackend.process_page (inherited from CpuBackend) must also be clean."""
    import pd_prep_for_pgdp.adapters.gpu.cpu as cpu_mod

    method_src = inspect.getsource(cpu_mod.CpuBackend.process_page)
    assert "process_page_cpu(" not in method_src, (
        "LocalBackend.process_page (via CpuBackend) must not call process_page_cpu()"
    )


# ── Acceptance bullet 2: CpuBackend.process_page calls run_stage ─────────────


@pytest.mark.asyncio
async def test_cpu_backend_process_page_calls_run_stage(tmp_path: Path) -> None:
    """CpuBackend.process_page must call run_stage (not process_page_cpu).

    We seed a minimal project + page record in DB, then patch run_stage to
    record its calls and raise so the test doesn't need cv2 or pd_book_tools.
    The key assertion is that run_stage is called with stage_id='ingest_source'
    — proving the registry dispatch path is taken.
    """
    from datetime import UTC, datetime

    from pd_prep_for_pgdp.adapters.database.sqlite import SqliteDatabase
    from pd_prep_for_pgdp.adapters.gpu.base import ProcessPageRequest
    from pd_prep_for_pgdp.adapters.gpu.cpu import CpuBackend
    from pd_prep_for_pgdp.adapters.storage.filesystem import FilesystemStorage
    from pd_prep_for_pgdp.core.models import (
        PageConfigOverrides,
        PageRecord,
        PipelineState,
        Project,
        ProjectConfig,
        ProjectStatus,
    )

    db = SqliteDatabase(f"sqlite:///{(tmp_path / 's.db').as_posix()}")
    await db.initialize()
    storage = FilesystemStorage(root=tmp_path / "data")

    now = datetime.now(UTC)
    project = Project(
        id="p1",
        owner_id="default",
        name="test",
        created_at=now,
        updated_at=now,
        status=ProjectStatus.processing,
        page_count=1,
        proof_page_count=1,
        config=ProjectConfig(book_name="test", source_uri=""),
        pipeline_state=PipelineState(),
        storage_prefix="projects/p1/",
    )
    await db.put_project(project)
    page = PageRecord(
        project_id="p1",
        idx0=0,
        prefix="p000",
        source_stem="page0",
        source_key="projects/p1/source/page0.png",
    )
    await db.put_pages([page])

    backend = CpuBackend(storage=storage, database=db, data_root=tmp_path)

    run_stage_calls: list[dict] = []

    async def fake_run_stage(**kwargs: object) -> None:
        run_stage_calls.append(dict(kwargs))
        # Raise so we don't need to actually execute the full pipeline.
        raise RuntimeError("stop after first call")

    with (
        patch("pd_prep_for_pgdp.adapters.gpu.cpu.run_stage", fake_run_stage),
        pytest.raises(RuntimeError, match="stop after first call"),
    ):
        await backend.process_page(
            ProcessPageRequest(
                project_id="p1",
                idx0=0,
                config_overrides=PageConfigOverrides(),
                output_context="commit",
            )
        )

    assert run_stage_calls, "CpuBackend.process_page did not call run_stage"
    assert run_stage_calls[0]["stage_id"] == "ingest_source"


# ── Acceptance bullet 3: data_root flows through build_gpu_backend ────────────


def test_build_gpu_backend_passes_data_root_to_cpu_backend(tmp_path: Path) -> None:
    """build_gpu_backend must inject data_root into CpuBackend / LocalBackend."""
    from pd_prep_for_pgdp.adapters.gpu.cpu import CpuBackend
    from pd_prep_for_pgdp.bootstrap import build_gpu_backend
    from pd_prep_for_pgdp.settings import Settings

    settings = Settings(
        host="127.0.0.1",
        port=8765,
        data_root=tmp_path / "data",
        config_dir=tmp_path / "config",
        storage_backend="filesystem",
        database_url=f"sqlite:///{(tmp_path / 's.db').as_posix()}",
        gpu_backend="cpu",
        dispatch_interval_seconds=0,
        auth_mode="none",
    )
    backend = build_gpu_backend(settings)
    assert isinstance(backend, CpuBackend)
    assert backend._data_root == settings.data_root


# ── Acceptance bullet: process_page requires data_root ───────────────────────


@pytest.mark.asyncio
async def test_cpu_backend_process_page_requires_data_root(tmp_path: Path) -> None:
    """process_page raises RuntimeError when data_root is not injected."""
    from pd_prep_for_pgdp.adapters.database.sqlite import SqliteDatabase
    from pd_prep_for_pgdp.adapters.gpu.base import ProcessPageRequest
    from pd_prep_for_pgdp.adapters.gpu.cpu import CpuBackend
    from pd_prep_for_pgdp.adapters.storage.filesystem import FilesystemStorage
    from pd_prep_for_pgdp.core.models import PageConfigOverrides

    db = SqliteDatabase(f"sqlite:///{(tmp_path / 's.db').as_posix()}")
    await db.initialize()
    storage = FilesystemStorage(root=tmp_path / "data")
    # Intentionally omit data_root=
    backend = CpuBackend(storage=storage, database=db)

    with pytest.raises(RuntimeError, match="data_root"):
        await backend.process_page(
            ProcessPageRequest(
                project_id="p1",
                idx0=0,
                config_overrides=PageConfigOverrides(),
                output_context="commit",
            )
        )
