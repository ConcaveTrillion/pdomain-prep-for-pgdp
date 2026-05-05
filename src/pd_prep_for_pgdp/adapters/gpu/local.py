"""In-process CUDA GPUBackend (CuPy + GPU PyTorch / DocTR)."""

from __future__ import annotations

from .base import (
    BatchJobItem,
    BatchJobResult,
    GPUBackend,
    OcrPageRequest,
    OcrPageResponse,
    ProcessPageRequest,
    ProcessPageResponse,
)


class LocalBackend(GPUBackend):
    name = "local"

    async def process_page(self, req: ProcessPageRequest) -> ProcessPageResponse:
        raise NotImplementedError("core.pipeline.process_page not yet wired")

    async def run_ocr(self, req: OcrPageRequest) -> OcrPageResponse:
        raise NotImplementedError("core.ocr.run_ocr not yet wired")

    async def run_batch(self, items: list[BatchJobItem]) -> list[BatchJobResult]:
        raise NotImplementedError("core.pipeline.run_batch not yet wired")
