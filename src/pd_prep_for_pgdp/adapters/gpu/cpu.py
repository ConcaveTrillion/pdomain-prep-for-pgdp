"""CPU GPUBackend — fallback when no CUDA / MPS is available.

Wires the request/response Protocol to `core.pipeline` (Step 4) and `core.ocr`
(DocTR via pd-book-tools). The same code runs on macOS arm64 too — DocTR
auto-uses MPS when torch sees Apple Silicon, so MPS is treated as a "CPU
backend" for adapter-selection purposes (the heavy CV ops still use cv2).

CPU mode is **first-class**, not degraded — see spec 09.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from pathlib import Path
from typing import Any

import anyio.to_thread

from ...core.config_resolver import resolve_page_config
from ...core.models import (
    OcrWord,
    PageRecord,
    SystemDefaults,
)
from ...core.pipeline.page_stage_writer import stage_artifact_path
from ...core.pipeline.stage_runner import run_stage
from ...core.queue.single_executor import Priority, SingleExecutor
from .base import (
    BatchJobItem,
    BatchJobResult,
    BatchProgressCb,
    GPUBackend,
    OcrPageRequest,
    OcrPageResponse,
    ProcessPageRequest,
    ProcessPageResponse,
)

log = logging.getLogger(__name__)

# Stages that produce the proofing image for a normal page (4c-4n).
# The runner also handles blank_proof_synth for blank pages; both paths
# terminate in a stage whose artifact is the proofing PNG. The shim runs
# all stages through the proofing terminal — the runner skips stages
# whose deps aren't clean (e.g. blank_proof_synth on a normal page).
_PROCESS_PAGE_STAGES: tuple[str, ...] = (
    "ingest_source",
    "auto_detect_attrs",
    "decode_source",
    "initial_crop",
    "manual_deskew_pre",
    "grayscale",
    "threshold",
    "invert",
    "find_content_edges",
    "crop_to_content",
    "auto_deskew",
    "morph_fill",
    "rescale",
    "canvas_map",
    "blank_proof_synth",
)

# Stage whose artifact is the final proofing PNG for a normal page.
_PROOFING_STAGE_NORMAL = "canvas_map"
# Stage whose artifact is the final proofing PNG for a blank/plate page.
_PROOFING_STAGE_BLANK = "blank_proof_synth"


class CpuBackend(GPUBackend):
    name = "cpu"

    def __init__(
        self,
        *,
        storage: Any | None = None,
        database: Any | None = None,
        executor: SingleExecutor | None = None,
        data_root: Path | None = None,
    ) -> None:
        # Optional: bootstrap.build_app may inject the storage/database
        # adapters so this backend can read source images and write outputs
        # without round-tripping through the route handler. Tests can leave
        # them None and use the in-memory paths.
        self._storage = storage
        self._database = database
        # Single-thread executor — workbench previews preempt batch passes.
        # The drain loop is started by build_app on the asyncio loop. Tests
        # that don't go through build_app fall back to anyio.to_thread.
        self._executor = executor
        # data_root is required for run_stage-based process_page (M5 #91).
        self._data_root = data_root

    async def process_page(self, req: ProcessPageRequest) -> ProcessPageResponse:
        """Shim: run per-page stages via STAGE_IMPL registry, return proofing URL.

        Replaces the former direct call to ``process_page_cpu``. Instead,
        runs each stage in ``_PROCESS_PAGE_STAGES`` through ``run_stage``
        (which dispatches via ``STAGE_IMPL[stage_id]['cpu']``). The runner
        skips stages whose deps aren't clean (e.g. ``blank_proof_synth``
        on a normal page raises ``StageDependenciesNotMet`` and the shim
        catches it to try the next candidate).

        After the stages run the shim reads the proofing artifact from the
        local stage store, copies it to the canonical storage key, and
        presigns a URL for the caller.
        """
        if self._storage is None or self._database is None:
            raise RuntimeError(
                "CpuBackend.process_page requires storage + database adapters (injected by build_app)."
            )
        if self._data_root is None:
            raise RuntimeError(
                "CpuBackend.process_page requires data_root (injected by build_app). "
                "Pass data_root= when constructing CpuBackend or use build_gpu_backend()."
            )

        _project_record, _system_defaults, page = await self._load_context(req.project_id, req.idx0)

        # Workbench overrides win over the persisted record for this call.
        if req.config_overrides is not None:
            page = page.model_copy(update={"config_overrides": req.config_overrides})

        page_id = f"{req.idx0:04d}"
        source_key = page.source_key or f"projects/{req.project_id}/source/{page.source_stem}"

        t0 = time.monotonic()

        # Run each process-page stage through the STAGE_IMPL registry.
        # Per-stage failures are tolerated when they arise from unmet
        # dependencies (e.g. blank_proof_synth on a normal page has no
        # clean auto_detect_attrs parent). Real impl failures propagate.
        from ...core.pipeline.stage_runner import StageDependenciesNotMet, StageRunFailed

        for stage_id in _PROCESS_PAGE_STAGES:
            try:
                await run_stage(
                    data_root=self._data_root,
                    database=self._database,
                    project_id=req.project_id,
                    page_id=page_id,
                    stage_id=stage_id,
                    device="cpu",
                    storage=self._storage,
                    page_source_key=source_key,
                )
            except StageDependenciesNotMet:
                # Expected for the alternate branch (e.g. blank_proof_synth
                # on a normal page, canvas_map on a blank page). Continue.
                continue
            except StageRunFailed:
                # Impl failure on a specific stage; re-raise so the route
                # handler can surface a clear error to the caller.
                raise

        # Read the proofing artifact from the local stage store.
        # Try the normal-page terminal first; fall back to blank-page.
        proofing_png: bytes | None = None
        proofing_h, proofing_w = 0, 0
        for candidate in (_PROOFING_STAGE_NORMAL, _PROOFING_STAGE_BLANK):
            path = stage_artifact_path(self._data_root, req.project_id, page_id, candidate)
            if path.exists():
                import cv2  # type: ignore[import-not-found]
                import numpy as np  # type: ignore[import-not-found]

                proofing_png = path.read_bytes()
                arr = np.frombuffer(proofing_png, dtype=np.uint8)
                img = cv2.imdecode(arr, cv2.IMREAD_UNCHANGED)
                if img is not None:
                    proofing_h, proofing_w = img.shape[:2]
                break

        if proofing_png is None:
            raise RuntimeError(
                f"process_page: no proofing artifact found after running stages "
                f"(project={req.project_id!r}, page={page_id!r})"
            )

        # Write proofing PNG to storage under the caller-appropriate key.
        if req.output_context == "workbench":
            out_key = f"projects/{req.project_id}/workbench_temp/{req.idx0}/proofing.png"
        else:
            out_key = f"projects/{req.project_id}/processed/{page.source_stem}_{page.prefix}.png"
        await self._storage.put_bytes(out_key, proofing_png, "image/png")
        url = await self._storage.presign_get(out_key)

        elapsed_ms = int((time.monotonic() - t0) * 1000)
        return ProcessPageResponse(
            processed_image_key=out_key,
            processed_image_url=url,
            dimensions=(proofing_h, proofing_w),
            processing_time_ms=elapsed_ms,
            backend="cpu",
            cold_start_ms=0,
        )

    async def run_ocr(self, req: OcrPageRequest) -> OcrPageResponse:
        """OCR a single page or a single split."""
        if self._storage is None or self._database is None:
            raise RuntimeError(
                "CpuBackend.run_ocr requires storage + database adapters (injected by build_app)."
            )

        project_record, system, page = await self._load_context(req.project_id, req.idx0)
        cfg = resolve_page_config(system, project_record.config, page)
        if req.engine is not None:
            cfg = cfg.model_copy(update={"ocr_engine": req.engine})

        # Locate the OCR-cropped image. process_page must have run first.
        full_prefix = f"{page.prefix}{req.split_suffix}" if req.split_suffix else page.prefix
        ocr_image_key = f"projects/{req.project_id}/ocr_images/{page.source_stem}_{full_prefix}.png"
        if not await self._storage.exists(ocr_image_key):
            raise FileNotFoundError(f"OCR-cropped image not found: {ocr_image_key} — run Step 6 first")
        img_bytes = await self._storage.get_bytes(ocr_image_key)

        priority = Priority.BATCH if req.batch_mode else Priority.INTERACTIVE
        if self._executor is not None:
            text, words = await self._executor.submit(
                priority, _ocr_image_bytes, img_bytes, cfg, system, req.split_suffix
            )
        else:
            text, words = await anyio.to_thread.run_sync(
                lambda: _ocr_image_bytes(img_bytes, cfg, system, req.split_suffix)
            )

        text_key = f"projects/{req.project_id}/ocr_text/{page.source_stem}_{full_prefix}.txt"
        await self._storage.put_bytes(text_key, text.encode("utf-8"), "text/plain")

        # Persist words alongside the text so the TextReviewPage overlay has
        # bboxes to render on a fresh page mount (P1 #6). Same key root,
        # `.words.json` suffix instead of `.txt`. Serialise via Pydantic so
        # the on-disk shape matches `list[OcrWord]` exactly.
        words_key = words_key_for(text_key)
        words_payload = json.dumps([w.model_dump(mode="json") for w in words]).encode("utf-8")
        await self._storage.put_bytes(words_key, words_payload, "application/json")

        return OcrPageResponse(text=text, words=words, text_key=text_key)

    async def run_batch(
        self,
        items: list[BatchJobItem],
        *,
        progress_cb: BatchProgressCb | None = None,
    ) -> list[BatchJobResult]:
        """Run a batch of jobs sequentially.

        CPU mode trades parallelism for simplicity — the pages are processed
        in order. The dispatcher is responsible for chunking; this method
        executes whatever it gets.

        When `progress_cb` is supplied, it is invoked after every item with
        `(current, total, result)` so callers can stream per-item progress
        events (the runner uses this for the JobEventBroker fan-out).
        """
        out: list[BatchJobResult] = []
        total = len(items)
        for item in items:
            try:
                if item.job_type == "batch_process_pages":
                    req = ProcessPageRequest(
                        project_id=item.project_id,
                        idx0=item.idx0,
                        config_overrides=item.payload.get("config_overrides") or _empty_overrides(),
                        output_context="commit",
                    )
                    resp = await self.process_page(req)
                    out.append(
                        BatchJobResult(
                            job_type=item.job_type,
                            project_id=item.project_id,
                            idx0=item.idx0,
                            ok=True,
                            payload={"processed_image_key": resp.processed_image_key},
                        )
                    )
                elif item.job_type == "batch_ocr":
                    req2 = OcrPageRequest(
                        project_id=item.project_id,
                        idx0=item.idx0,
                        split_suffix=item.payload.get("split_suffix"),
                    )
                    resp2 = await self.run_ocr(req2)
                    out.append(
                        BatchJobResult(
                            job_type=item.job_type,
                            project_id=item.project_id,
                            idx0=item.idx0,
                            ok=True,
                            payload={"text_key": resp2.text_key},
                        )
                    )
                else:
                    out.append(
                        BatchJobResult(
                            job_type=item.job_type,
                            project_id=item.project_id,
                            idx0=item.idx0,
                            ok=False,
                            error=f"unsupported job_type: {item.job_type}",
                        )
                    )
            except Exception as e:
                log.exception("batch item failed: %s idx0=%s", item.job_type, item.idx0)
                out.append(
                    BatchJobResult(
                        job_type=item.job_type,
                        project_id=item.project_id,
                        idx0=item.idx0,
                        ok=False,
                        error=str(e),
                    )
                )
            if progress_cb is not None:
                # Fire-and-tolerate: a busted callback shouldn't abort the batch.
                try:
                    await progress_cb(len(out), total, out[-1])
                except Exception:
                    log.exception("run_batch progress_cb raised (item idx0=%s); continuing", item.idx0)
            await asyncio.sleep(0)  # yield to other tasks
        return out

    # ── Helpers ────────────────────────────────────────────────────────────

    async def _load_context(self, project_id: str, idx0: int) -> tuple[Any, SystemDefaults, PageRecord]:
        project = await self._database.get_project(project_id)
        if project is None:
            raise FileNotFoundError(f"project not found: {project_id}")
        page = await self._database.get_page(project_id, idx0)
        if page is None:
            raise FileNotFoundError(f"page not found: {project_id}/{idx0}")
        system = await self._database.get_system_defaults(project.owner_id)
        return project, system, page


# ─── Module-level helpers (module-scope so they can run on a thread) ────────


def words_key_for(text_key: str) -> str:
    """Sibling words-blob key for an OCR text key.

    `<root>.txt` -> `<root>.words.json`. If the text key doesn't end in
    `.txt` (shouldn't happen, but be defensive), we still append the
    suffix so the words blob is co-located with the text.
    """
    if text_key.endswith(".txt"):
        return text_key[:-4] + ".words.json"
    return text_key + ".words.json"


def load_words_from_storage(raw: bytes) -> list[OcrWord]:
    """Decode the on-disk words blob into a list of `OcrWord`."""
    items = json.loads(raw.decode("utf-8"))
    return [OcrWord.model_validate(item) for item in items]


def _ocr_image_bytes(
    img_bytes: bytes,
    cfg: Any,
    system: SystemDefaults,
    split_suffix: str | None,
) -> tuple[str, list[Any]]:
    """OCR raw PNG bytes via core.ocr.ocr_page (writes to a temp file first)."""
    import tempfile

    from ...core.ocr import ocr_page

    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
        tmp.write(img_bytes)
        tmp_path = Path(tmp.name)
    try:
        result = ocr_page(tmp_path, cfg=cfg, system=system)
    finally:
        tmp_path.unlink(missing_ok=True)
    if split_suffix:
        for w in result.words:
            w.split_suffix = split_suffix
    return result.text, result.words


def _empty_overrides() -> Any:
    from ...core.models import PageConfigOverrides

    return PageConfigOverrides()
