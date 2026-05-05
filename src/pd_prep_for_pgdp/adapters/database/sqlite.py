"""SQLite-backed IDatabase implementation.

Uses stdlib `sqlite3` (no external deps). One JSON-text column per record
shape — schema migrations stay trivial since we treat the rows as document
storage. This matches the local-mode goal of zero-extra-dependency install.
"""

from __future__ import annotations

import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path

import anyio.to_thread

from ...core.models import Job, PageRecord, Project, SystemDefaults

_SCHEMA = """
CREATE TABLE IF NOT EXISTS system_defaults (
    owner_id TEXT PRIMARY KEY,
    body     TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS projects (
    id        TEXT PRIMARY KEY,
    owner_id  TEXT NOT NULL,
    body      TEXT NOT NULL,
    updated_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS projects_owner ON projects(owner_id);

CREATE TABLE IF NOT EXISTS pages (
    project_id TEXT NOT NULL,
    idx0       INTEGER NOT NULL,
    body       TEXT NOT NULL,
    PRIMARY KEY (project_id, idx0)
);

CREATE TABLE IF NOT EXISTS jobs (
    id         TEXT PRIMARY KEY,
    owner_id   TEXT NOT NULL,
    body       TEXT NOT NULL,
    created_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS jobs_owner_created ON jobs(owner_id, created_at DESC);
"""


class SqliteDatabase:
    def __init__(self, url: str) -> None:
        # Accept "sqlite:///abs/path" or "sqlite:///:memory:".
        prefix = "sqlite:///"
        if not url.startswith(prefix):
            raise ValueError(f"unrecognised SQLite URL: {url!r}")
        path = url[len(prefix) :]
        self._memory = path == ":memory:"
        self._path = path if self._memory else str(Path(path).expanduser())
        self._conn: sqlite3.Connection | None = None
        # SQLite connection isn't safe to share across threads without a lock.
        # The runner now fans out concurrent jobs (max_concurrency > 1) so
        # two threads can race on commit() without this guard.
        self._write_lock = threading.Lock()

    # ── Lifecycle ───────────────────────────────────────────────────────────

    async def initialize(self) -> None:
        await anyio.to_thread.run_sync(self._initialize_sync)

    def _initialize_sync(self) -> None:
        if not self._memory:
            Path(self._path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self._path, check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode = WAL;")
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    async def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    @contextmanager
    def _cursor(self):
        assert self._conn is not None, "Database not initialised"
        with self._write_lock:
            cur = self._conn.cursor()
            try:
                yield cur
                self._conn.commit()
            finally:
                cur.close()

    async def _run(self, fn, *args):  # type: ignore[no-untyped-def]
        return await anyio.to_thread.run_sync(lambda: fn(*args))

    # ── System defaults ─────────────────────────────────────────────────────

    async def get_system_defaults(self, owner_id: str) -> SystemDefaults:
        def _go() -> SystemDefaults:
            with self._cursor() as cur:
                row = cur.execute(
                    "SELECT body FROM system_defaults WHERE owner_id = ?", (owner_id,)
                ).fetchone()
                if row is None:
                    return SystemDefaults()
                return SystemDefaults.model_validate_json(row[0])

        return await self._run(_go)

    async def put_system_defaults(self, owner_id: str, defaults: SystemDefaults) -> None:
        body = defaults.model_dump_json()

        def _go() -> None:
            with self._cursor() as cur:
                cur.execute(
                    "INSERT OR REPLACE INTO system_defaults (owner_id, body) VALUES (?, ?)",
                    (owner_id, body),
                )

        await self._run(_go)

    # ── Projects ────────────────────────────────────────────────────────────

    async def list_projects(self, owner_id: str) -> list[Project]:
        def _go() -> list[Project]:
            with self._cursor() as cur:
                rows = cur.execute(
                    "SELECT body FROM projects WHERE owner_id = ? ORDER BY updated_at DESC",
                    (owner_id,),
                ).fetchall()
                return [Project.model_validate_json(r[0]) for r in rows]

        return await self._run(_go)

    async def get_project(self, project_id: str) -> Project | None:
        def _go() -> Project | None:
            with self._cursor() as cur:
                row = cur.execute(
                    "SELECT body FROM projects WHERE id = ?", (project_id,)
                ).fetchone()
                return Project.model_validate_json(row[0]) if row else None

        return await self._run(_go)

    async def put_project(self, project: Project) -> None:
        body = project.model_dump_json()
        ts = project.updated_at.timestamp()

        def _go() -> None:
            with self._cursor() as cur:
                cur.execute(
                    "INSERT OR REPLACE INTO projects (id, owner_id, body, updated_at) "
                    "VALUES (?, ?, ?, ?)",
                    (project.id, project.owner_id, body, ts),
                )

        await self._run(_go)

    async def delete_project(self, project_id: str) -> None:
        def _go() -> None:
            with self._cursor() as cur:
                cur.execute("DELETE FROM pages WHERE project_id = ?", (project_id,))
                cur.execute("DELETE FROM projects WHERE id = ?", (project_id,))

        await self._run(_go)

    # ── Pages ───────────────────────────────────────────────────────────────

    async def list_pages(
        self,
        project_id: str,
        cursor: str | None = None,
        limit: int = 50,
    ) -> tuple[list[PageRecord], str | None, int]:
        def _go() -> tuple[list[PageRecord], str | None, int]:
            offset = int(cursor) if cursor else 0
            with self._cursor() as cur:
                total = cur.execute(
                    "SELECT COUNT(*) FROM pages WHERE project_id = ?", (project_id,)
                ).fetchone()[0]
                rows = cur.execute(
                    "SELECT body FROM pages WHERE project_id = ? "
                    "ORDER BY idx0 LIMIT ? OFFSET ?",
                    (project_id, limit, offset),
                ).fetchall()
            pages = [PageRecord.model_validate_json(r[0]) for r in rows]
            next_cursor = str(offset + limit) if offset + limit < total else None
            return pages, next_cursor, total

        return await self._run(_go)

    async def get_page(self, project_id: str, idx0: int) -> PageRecord | None:
        def _go() -> PageRecord | None:
            with self._cursor() as cur:
                row = cur.execute(
                    "SELECT body FROM pages WHERE project_id = ? AND idx0 = ?",
                    (project_id, idx0),
                ).fetchone()
                return PageRecord.model_validate_json(row[0]) if row else None

        return await self._run(_go)

    async def put_page(self, page: PageRecord) -> None:
        body = page.model_dump_json()

        def _go() -> None:
            with self._cursor() as cur:
                cur.execute(
                    "INSERT OR REPLACE INTO pages (project_id, idx0, body) VALUES (?, ?, ?)",
                    (page.project_id, page.idx0, body),
                )

        await self._run(_go)

    async def put_pages(self, pages: list[PageRecord]) -> None:
        if not pages:
            return
        rows = [(p.project_id, p.idx0, p.model_dump_json()) for p in pages]

        def _go() -> None:
            with self._cursor() as cur:
                cur.executemany(
                    "INSERT OR REPLACE INTO pages (project_id, idx0, body) VALUES (?, ?, ?)",
                    rows,
                )

        await self._run(_go)

    # ── Jobs ────────────────────────────────────────────────────────────────

    async def get_job(self, job_id: str) -> Job | None:
        def _go() -> Job | None:
            with self._cursor() as cur:
                row = cur.execute("SELECT body FROM jobs WHERE id = ?", (job_id,)).fetchone()
                return Job.model_validate_json(row[0]) if row else None

        return await self._run(_go)

    async def put_job(self, job: Job) -> None:
        body = job.model_dump_json()
        ts = job.created_at.timestamp()

        def _go() -> None:
            with self._cursor() as cur:
                cur.execute(
                    "INSERT OR REPLACE INTO jobs (id, owner_id, body, created_at) "
                    "VALUES (?, ?, ?, ?)",
                    (job.id, job.owner_id, body, ts),
                )

        await self._run(_go)

    async def list_recent_jobs(self, owner_id: str, limit: int = 50) -> list[Job]:
        def _go() -> list[Job]:
            with self._cursor() as cur:
                rows = cur.execute(
                    "SELECT body FROM jobs WHERE owner_id = ? "
                    "ORDER BY created_at DESC LIMIT ?",
                    (owner_id, limit),
                ).fetchall()
            return [Job.model_validate_json(r[0]) for r in rows]

        return await self._run(_go)
