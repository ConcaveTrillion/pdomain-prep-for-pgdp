"""IDatabase Protocol.

Persists structured records: projects, pages, jobs, system defaults. The image
files themselves live on `IStorage`. In filesystem-storage / SQLite mode the
database is a small companion to the JSON files on disk; in Postgres mode the
JSON files are not written and the DB is authoritative.
"""

from __future__ import annotations

from typing import Protocol

from ...core.models import Job, PageRecord, Project, SystemDefaults


class IDatabase(Protocol):
    # ── Lifecycle ───────────────────────────────────────────────────────────
    async def initialize(self) -> None: ...

    async def close(self) -> None: ...

    # ── System defaults ─────────────────────────────────────────────────────
    async def get_system_defaults(self, owner_id: str) -> SystemDefaults: ...

    async def put_system_defaults(self, owner_id: str, defaults: SystemDefaults) -> None: ...

    # ── Projects ────────────────────────────────────────────────────────────
    async def list_projects(self, owner_id: str) -> list[Project]: ...

    async def get_project(self, project_id: str) -> Project | None: ...

    async def put_project(self, project: Project) -> None: ...

    async def delete_project(self, project_id: str) -> None: ...

    # ── Pages ───────────────────────────────────────────────────────────────
    async def list_pages(
        self,
        project_id: str,
        cursor: str | None = None,
        limit: int = 50,
    ) -> tuple[list[PageRecord], str | None, int]: ...

    async def get_page(self, project_id: str, idx0: int) -> PageRecord | None: ...

    async def put_page(self, page: PageRecord) -> None: ...

    async def put_pages(self, pages: list[PageRecord]) -> None: ...

    # ── Jobs ────────────────────────────────────────────────────────────────
    async def get_job(self, job_id: str) -> Job | None: ...

    async def put_job(self, job: Job) -> None: ...

    async def list_recent_jobs(self, owner_id: str, limit: int = 50) -> list[Job]: ...
