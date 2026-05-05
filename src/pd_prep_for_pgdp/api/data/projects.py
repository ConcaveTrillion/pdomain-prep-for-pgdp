"""/api/data/projects/* — project CRUD."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ...adapters.auth import UserContext
from ...adapters.database import IDatabase
from ...adapters.storage import IStorage
from ...core.models import (
    PipelineState,
    Project,
    ProjectConfig,
    ProjectStatus,
)
from ..dependencies import get_database, get_storage, get_user

router = APIRouter(tags=["projects"])


class CreateProjectRequest(BaseModel):
    name: str
    source_type: Literal["zip", "s3_folder", "local_folder"]
    source_uri: str | None = None


class CreateProjectResponse(BaseModel):
    project: Project
    upload_url: str | None = None
    upload_key: str | None = None


class UpdateConfigRequest(BaseModel):
    project_config: dict[str, Any]
    name: str | None = None
    """Optional rename. Lifts both `Project.name` and `ProjectConfig.book_name`."""


class UpdateConfigResponse(BaseModel):
    project_config: ProjectConfig
    updated_at: datetime


@router.post("/projects", response_model=CreateProjectResponse)
async def create_project(
    body: CreateProjectRequest,
    user: UserContext = Depends(get_user),
    db: IDatabase = Depends(get_database),
    storage: IStorage = Depends(get_storage),
) -> CreateProjectResponse:
    project_id = uuid.uuid4().hex
    now = datetime.now(UTC)

    config = ProjectConfig(
        book_name=body.name,
        source_uri=body.source_uri or "",
    )
    project = Project(
        id=project_id,
        owner_id=user.user_id,
        name=body.name,
        created_at=now,
        updated_at=now,
        status=ProjectStatus.ingesting,
        page_count=0,
        proof_page_count=0,
        config=config,
        pipeline_state=PipelineState(),
        storage_prefix=f"projects/{project_id}/",
    )
    await db.put_project(project)

    upload_url: str | None = None
    upload_key: str | None = None
    if body.source_type == "zip":
        upload_key = f"projects/{project_id}/source.zip"
        upload_url = await storage.presign_put(upload_key, "application/zip")

    return CreateProjectResponse(
        project=project, upload_url=upload_url, upload_key=upload_key
    )


@router.get("/projects", response_model=list[Project])
async def list_projects(
    user: UserContext = Depends(get_user),
    db: IDatabase = Depends(get_database),
) -> list[Project]:
    return await db.list_projects(user.user_id)


@router.get("/projects/{project_id}", response_model=Project)
async def get_project(
    project_id: str,
    user: UserContext = Depends(get_user),
    db: IDatabase = Depends(get_database),
) -> Project:
    project = await db.get_project(project_id)
    if project is None:
        raise HTTPException(404, "project not found")
    if project.owner_id != user.user_id:
        raise HTTPException(403, "not authorised")
    return project


@router.patch(
    "/projects/{project_id}/config",
    response_model=UpdateConfigResponse,
)
async def update_project_config(
    project_id: str,
    body: UpdateConfigRequest,
    user: UserContext = Depends(get_user),
    db: IDatabase = Depends(get_database),
) -> UpdateConfigResponse:
    project = await db.get_project(project_id)
    if project is None:
        raise HTTPException(404, "project not found")
    if project.owner_id != user.user_id:
        raise HTTPException(403, "not authorised")
    merged = project.config.model_dump()
    merged.update(body.project_config)
    # `name` is normally a top-level Project field, but conceptually it's the
    # same data as `book_name`. Keep them in sync — whichever the caller sends
    # wins, with explicit `name` taking priority over `project_config.book_name`.
    new_name = body.name or merged.get("book_name")
    if new_name:
        merged["book_name"] = new_name
    project.config = ProjectConfig.model_validate(merged)
    if new_name:
        project.name = new_name
    project.updated_at = datetime.now(UTC)
    await db.put_project(project)
    # Re-derive prefixes whenever ranges change. Cheap (in-memory walk).
    from ...core.assign_prefixes import assign_prefixes

    await assign_prefixes(project=project, database=db)
    return UpdateConfigResponse(
        project_config=project.config,
        updated_at=project.updated_at,
    )


@router.delete("/projects/{project_id}", status_code=204)
async def delete_project(
    project_id: str,
    user: UserContext = Depends(get_user),
    db: IDatabase = Depends(get_database),
) -> None:
    project = await db.get_project(project_id)
    if project is None:
        return
    if project.owner_id != user.user_id:
        raise HTTPException(403, "not authorised")
    await db.delete_project(project_id)
