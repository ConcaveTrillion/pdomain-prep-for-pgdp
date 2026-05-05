"""Modal GPUBackend — dispatches GPU work to a Modal Function.

Two pieces:

1. **Modal app** (`modal_app.py` next to this file) — the actual Modal
   container definition. Imports `pd_prep_for_pgdp.core.pipeline` and
   `core.ocr` so the same code runs locally and in Modal. Deployed via:
       modal deploy src/pd_prep_for_pgdp/adapters/gpu/modal_app.py

2. **`ModalBackend`** (this file) — the `GPUBackend` Protocol implementation
   that the FastAPI process uses to dispatch. It loads the deployed Modal
   functions by name (`Function.lookup("pgdp-prep", "process_page")`) and
   invokes them via `.remote()` for sync calls or `.spawn().get()` for async
   batch flows.

In managed mode the FastAPI container is CPU-only — every GPU call goes
through here. Cold starts are amortised by the BatchDispatcher (spec 09).

This module imports `modal` lazily so the [modal] extra stays optional.
"""

from __future__ import annotations

import logging
from typing import Any

from .base import (
    BatchJobItem,
    BatchJobResult,
    GPUBackend,
    OcrPageRequest,
    OcrPageResponse,
    ProcessPageRequest,
    ProcessPageResponse,
)

log = logging.getLogger(__name__)


class ModalBackend(GPUBackend):
    name = "modal"

    APP_NAME = "pgdp-prep"
    PROCESS_PAGE_FN = "process_page"
    RUN_OCR_FN = "run_ocr"
    RUN_BATCH_FN = "run_batch"

    def __init__(self, token_id: str, token_secret: str) -> None:
        self._token_id = token_id
        self._token_secret = token_secret
        self._fns: dict[str, Any] = {}

    # ── Lazy function loading ──────────────────────────────────────────────

    def _load_function(self, fn_name: str) -> Any:
        """Look up a deployed Modal function by name; cache the handle."""
        cached = self._fns.get(fn_name)
        if cached is not None:
            return cached
        try:
            from modal import Function  # type: ignore[import-not-found]
        except ImportError as e:
            raise RuntimeError(
                "Modal backend requires the [modal] extra: "
                "install with 'pip install pd-prep-for-pgdp[modal]'"
            ) from e

        # Modal v0.66+ uses Function.lookup(app_name, fn_name).
        fn = Function.lookup(self.APP_NAME, fn_name)
        self._fns[fn_name] = fn
        return fn

    # ── GPUBackend Protocol ────────────────────────────────────────────────

    async def process_page(self, req: ProcessPageRequest) -> ProcessPageResponse:
        fn = self._load_function(self.PROCESS_PAGE_FN)
        # `.remote.aio()` is Modal's async dispatch; payload crosses the wire
        # as a JSON-serialisable dict so the Pydantic model survives.
        result = await fn.remote.aio(req.model_dump())
        return ProcessPageResponse.model_validate(result)

    async def run_ocr(self, req: OcrPageRequest) -> OcrPageResponse:
        fn = self._load_function(self.RUN_OCR_FN)
        result = await fn.remote.aio(req.model_dump())
        return OcrPageResponse.model_validate(result)

    async def run_batch(self, items: list[BatchJobItem]) -> list[BatchJobResult]:
        """One Modal invocation handles the whole batch — amortises cold start.

        Items must serialise to a list of plain dicts. Modal's container picks
        them up, runs `core.pipeline` / `core.ocr` per item, and returns a
        list of result dicts.
        """
        fn = self._load_function(self.RUN_BATCH_FN)
        payload = [item.model_dump() for item in items]
        results = await fn.remote.aio(payload)
        return [BatchJobResult.model_validate(r) for r in results]
