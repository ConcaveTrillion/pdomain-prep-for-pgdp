"""M1 §C — `GET /api/data/projects/{id}/pages/{idx0}/stages`.

Spec: `docs/specs/pipeline-task-model.md` §"API surface" (§Per-page
stage routes) + §"Dual-write reconciliation" (Q1-followup).

The route lazy-initialises 22 ``not-run`` rows on first read. The init
is idempotent and concurrency-safe (INSERT OR IGNORE on the composite
PK), so concurrent first-touches converge to exactly 22 rows, not 44.
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from pd_prep_for_pgdp.adapters.database.sqlite import SqliteDatabase
from pd_prep_for_pgdp.bootstrap import build_app
from pd_prep_for_pgdp.core.models import (
    PAGE_STAGE_IDS,
    PageProcessingStatus,
    PageRecord,
    PageStageStatus,
    PipelineState,
    Project,
    ProjectConfig,
    ProjectStatus,
)
from pd_prep_for_pgdp.core.pipeline.stage_dag import topological_order
from pd_prep_for_pgdp.settings import Settings


def _settings(tmp_path: Path) -> Settings:
    return Settings(
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


def _seed(settings: Settings, owner_id: str = "default") -> None:
    async def go() -> None:
        db = SqliteDatabase(settings.derived_database_url)
        await db.initialize()
        now = datetime.now(UTC)
        await db.put_project(
            Project(
                id="m1c",
                owner_id=owner_id,
                name="m1c",
                created_at=now,
                updated_at=now,
                status=ProjectStatus.processing,
                page_count=2,
                proof_page_count=2,
                config=ProjectConfig(book_name="m1c", source_uri=""),
                pipeline_state=PipelineState(),
                storage_prefix="projects/m1c/",
            )
        )
        await db.put_pages(
            [
                PageRecord(
                    project_id="m1c",
                    idx0=0,
                    prefix="p001",
                    source_stem="src1",
                    processing_status=PageProcessingStatus.pending,
                ),
                PageRecord(
                    project_id="m1c",
                    idx0=1,
                    prefix="p002",
                    source_stem="src2",
                    processing_status=PageProcessingStatus.pending,
                ),
            ]
        )
        await db.close()

    asyncio.run(go())


@pytest.fixture
def seeded_client(tmp_path: Path) -> Iterator[tuple[TestClient, Settings]]:
    settings = _settings(tmp_path)
    _seed(settings)
    app = build_app(settings)
    with TestClient(app) as c:
        yield c, settings


# ─── Happy path: lazy init + 22 ordered rows ────────────────────────────────


def test_list_page_stages_returns_22_not_run_on_first_read(
    seeded_client: tuple[TestClient, Settings],
) -> None:
    client, _ = seeded_client
    r = client.get("/api/data/projects/m1c/pages/0/stages")
    assert r.status_code == 200, r.text
    rows = r.json()
    assert isinstance(rows, list)
    assert len(rows) == 22
    for row in rows:
        assert row["status"] == PageStageStatus.not_run.value
        assert row["stage_version"] == 1
        assert row["artifact_key"] is None
        assert row["project_id"] == "m1c"
        assert row["page_id"] == "0000"


def test_list_page_stages_topological_order(
    seeded_client: tuple[TestClient, Settings],
) -> None:
    """Stage IDs must arrive in `topological_order()`."""
    client, _ = seeded_client
    r = client.get("/api/data/projects/m1c/pages/0/stages")
    assert r.status_code == 200
    got_ids = [row["stage_id"] for row in r.json()]
    expected_ids = [s.id for s in topological_order()]
    assert got_ids == expected_ids


def test_list_page_stages_ids_match_canonical_set(
    seeded_client: tuple[TestClient, Settings],
) -> None:
    """The 22 stage_ids must match `PAGE_STAGE_IDS` exactly (no dupes/typos)."""
    client, _ = seeded_client
    r = client.get("/api/data/projects/m1c/pages/0/stages")
    got = {row["stage_id"] for row in r.json()}
    assert got == set(PAGE_STAGE_IDS)


# ─── Idempotency: second call returns the same 22 rows ─────────────────────


def test_list_page_stages_second_call_no_duplicates(
    seeded_client: tuple[TestClient, Settings],
) -> None:
    client, _ = seeded_client
    r1 = client.get("/api/data/projects/m1c/pages/0/stages")
    r2 = client.get("/api/data/projects/m1c/pages/0/stages")
    assert r1.status_code == 200 and r2.status_code == 200
    assert len(r1.json()) == 22
    assert len(r2.json()) == 22
    # Row identities (project, page, stage) match across both responses.
    keys1 = sorted((r["project_id"], r["page_id"], r["stage_id"]) for r in r1.json())
    keys2 = sorted((r["project_id"], r["page_id"], r["stage_id"]) for r in r2.json())
    assert keys1 == keys2


def test_list_page_stages_concurrent_first_touch_is_idempotent(
    tmp_path: Path,
) -> None:
    """Two simultaneous first-touch reads must converge to exactly 22 rows.

    The lazy-init goes through `INSERT OR IGNORE` against the composite
    PK, so a concurrent racer's inserts no-op against the first
    inserter's rows. We use the in-process httpx-via-TestClient parallel
    pattern (asyncio.gather with the underlying ASGI transport) to
    exercise this without needing a real TCP server.
    """
    settings = _settings(tmp_path)
    _seed(settings)
    app = build_app(settings)

    async def hit_twice() -> tuple[int, int]:
        from httpx import ASGITransport, AsyncClient

        async with (
            # FastAPI lifespan runs on connection / first request, but
            # for a pure-app test we don't need it: list_page_stages
            # uses sqlite directly via app.state.database, which is
            # initialised by the lifespan. Use the sync TestClient as
            # context manager once to run startup, then issue async
            # parallel calls against the same app.
            AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as client,
        ):
            results = await asyncio.gather(
                client.get("/api/data/projects/m1c/pages/0/stages"),
                client.get("/api/data/projects/m1c/pages/0/stages"),
            )
            return (
                results[0].status_code,
                results[1].status_code,
                [
                    len(results[0].json()),
                    len(results[1].json()),
                ],
                [
                    sorted(r["stage_id"] for r in results[0].json()),
                    sorted(r["stage_id"] for r in results[1].json()),
                ],
            )

    # We need lifespan startup to initialise the DB before the parallel calls.
    with TestClient(app):
        s1, s2, lengths, ids = asyncio.run(hit_twice())

    assert s1 == 200 and s2 == 200
    assert lengths == [22, 22], f"expected each parallel response to have 22 rows, got {lengths}"
    assert ids[0] == ids[1], "concurrent first-touch produced different row sets"


# ─── 404 surfaces ──────────────────────────────────────────────────────────


def test_list_page_stages_404_unknown_project(
    seeded_client: tuple[TestClient, Settings],
) -> None:
    client, _ = seeded_client
    r = client.get("/api/data/projects/no-such-proj/pages/0/stages")
    assert r.status_code == 404


def test_list_page_stages_404_unknown_page(
    seeded_client: tuple[TestClient, Settings],
) -> None:
    client, _ = seeded_client
    r = client.get("/api/data/projects/m1c/pages/999/stages")
    assert r.status_code == 404


def test_list_page_stages_404_other_users_project(tmp_path: Path) -> None:
    """A project owned by user X is not visible to user Y."""
    settings = _settings(tmp_path)
    _seed(settings, owner_id="other-user")
    app = build_app(settings)
    with TestClient(app) as client:
        # The default `auth_mode=none` resolves the request to user_id="default"
        # — which doesn't match the seeded owner "other-user".
        r = client.get("/api/data/projects/m1c/pages/0/stages")
    assert r.status_code == 404, r.text


# ─── Persistence: rows materialised survive restart ─────────────────────────


def test_list_page_stages_persists_rows_to_db(tmp_path: Path) -> None:
    """After the route lazy-inits 22 rows, they must be visible via direct DB query."""
    settings = _settings(tmp_path)
    _seed(settings)
    app = build_app(settings)
    with TestClient(app) as client:
        r = client.get("/api/data/projects/m1c/pages/0/stages")
        assert r.status_code == 200
        assert len(r.json()) == 22

    # Re-open a fresh DB connection to confirm persistence across the
    # in-process app teardown.
    async def _check() -> int:
        db = SqliteDatabase(settings.derived_database_url)
        await db.initialize()
        rows = await db.list_page_stages_for_page("m1c", "0000")
        await db.close()
        return len(rows)

    assert asyncio.run(_check()) == 22
