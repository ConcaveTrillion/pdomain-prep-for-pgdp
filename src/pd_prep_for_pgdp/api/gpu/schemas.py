"""Wire shapes for /api/gpu/*. Pydantic source-of-truth for the OpenAPI client."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel

from ...adapters.gpu.base import (
    OcrPageRequest,
    OcrPageResponse,
    ProcessPageRequest,
    ProcessPageResponse,
)
from ...core.models import JobStatus

__all__ = [
    "BatchJobRequest",
    "BatchJobResponse",
    "IngestRequest",
    "JobResponse",
    "OcrPageRequest",
    "OcrPageResponse",
    "ProcessPageRequest",
    "ProcessPageResponse",
]


class IngestRequest(BaseModel):
    project_id: str
    source_key: str
    source_type: Literal["zip", "s3_folder", "local_folder"]


class JobResponse(BaseModel):
    job_id: str
    status: Literal["queued", "running"] = "queued"


class BatchJobRequest(BaseModel):
    project_id: str
    job_type: Literal[
        "batch_process_pages",
        "batch_ocr",
        "batch_text_postprocess",
        "batch_extract_illustrations",
        "build_package",
    ]
    page_idxs: list[int] | None = None


class BatchJobResponse(BaseModel):
    job_id: str
    status: JobStatus
    estimated_pages: int = 0
    dispatch_mode: Literal["immediate", "scheduled"] = "immediate"
    next_dispatch_at: datetime | None = None
