"""GPU backend: local CUDA / CPU / Modal / shared-container."""

from .base import (
    BatchJobItem,
    BatchJobResult,
    GPUBackend,
    OcrPageRequest,
    OcrPageResponse,
    ProcessPageRequest,
    ProcessPageResponse,
)

__all__ = [
    "BatchJobItem",
    "BatchJobResult",
    "GPUBackend",
    "OcrPageRequest",
    "OcrPageResponse",
    "ProcessPageRequest",
    "ProcessPageResponse",
]
