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
    "RetryJobRequest",
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


class RetryJobRequest(BaseModel):
    """Optional body for `POST /api/gpu/jobs/{id}/retry`.

    `payload_override`, when non-null, is shallow-merged over the original
    job's payload — keys present in the override replace the corresponding
    keys; keys not present are preserved from the original. The original
    job is never mutated, so the audit trail stays intact.
    """

    payload_override: dict | None = None
