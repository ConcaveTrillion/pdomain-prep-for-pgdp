# Spec 04 — GPU Acceleration

## Summary

Two pipeline stages are GPU-accelerated:

1. **Step 4 image processing** — grayscale, threshold, invert, edge-finding,
   deskew, morph, rescale, canvas placement (CuPy)
2. **Step 7 OCR** — DocTR uses PyTorch CUDA when available

GPU is **optional everywhere**. The pipeline runs end-to-end on CPU; the user
just waits longer. There is no feature that requires a GPU.

The `GPUBackend` interface (selected at startup) decides where GPU work
actually executes:

| Backend | Where compute runs | Selected by |
|---|---|---|
| `local` | Same process, in-place CuPy + CUDA PyTorch | `PGDP_GPU_BACKEND=local` (auto if CUDA detected at startup) |
| `mps` | Same process, CPU image processing + MPS PyTorch (DocTR only) | `PGDP_GPU_BACKEND=mps` (auto on macOS arm64) |
| `cpu` | Same process, NumPy/cv2 + CPU PyTorch | `PGDP_GPU_BACKEND=cpu` (auto when no CUDA, no MPS) |
| `modal` | Modal serverless function | `PGDP_GPU_BACKEND=modal` |
| `shared_container` | A long-running GPU ECS task shared across tenants | `PGDP_GPU_BACKEND=shared_container` |

The PyTorch wheel that determines which of `local`/`mps`/`cpu` is available is
chosen **at install time** by `install.sh` (spec 09): NVIDIA CUDA detected
via `nvidia-smi` → matching `cuXXX` index + `[cuda]` extra (which adds CuPy
and nvImageCodec); macOS arm64 → default wheel (MPS already supported); else
CPU wheel only. `PGDP_GPU_BACKEND` defaults to whichever is detected at
process startup, but can be overridden.

All backends implement the same protocol and call the same `core/pipeline/*`
functions. The Modal worker imports `core.pipeline.run_page_pipeline` directly;
the shared container is just a stripped-down `pgdp-prep` running with
`PGDP_MODE=gpu_worker_only`.

---

## GPU Detection

```python
def gpu_available() -> bool:
    try:
        import cupy
        return cupy.cuda.runtime.getDeviceCount() > 0
    except Exception:
        return False
```

At startup, the bootstrap module picks `local` (if CUDA detected) or `cpu`
(if not) when `PGDP_GPU_BACKEND` is unset. The user can override.

---

## Backend 1 — `local` (in-process CuPy)

Used by local installs with a CUDA GPU and self-hosted deployments on a
single GPU box.

The pipeline functions accept either a NumPy or CuPy array and dispatch
accordingly via `isinstance(img, cp.ndarray)`. The CPU fallback path is
selected by importing the cv2 functions instead of the cupy functions:

```python
# core/pipeline/_dispatch.py
if gpu_available():
    from pd_book_tools.image_processing.cupy_processing import (
        np_uint8_float_colorToGray   as _colorToGray,
        np_uint8_find_edges          as _find_edges,
        np_uint8_auto_deskew         as _auto_deskew,
        np_uint8_float_binary_thresh as _threshold,
    )
else:
    from pd_book_tools.image_processing.cv2_processing import (
        cv2_convert_to_grayscale as _colorToGray,
        find_edges               as _find_edges,
        auto_deskew              as _auto_deskew,
        otsu_binary_thresh       as _threshold,
    )
```

This is the only place the GPU-vs-CPU split happens in pipeline code.

### Existing pd-book-tools GPU functions

| Function | Module | CPU equivalent it replaces |
|---|---|---|
| `np_uint8_float_colorToGray` | `cupy_processing/colorToGray.py` | `run_gegl_c2g` (~30s/image → <1s) |
| `np_uint8_float_binary_thresh` | `cupy_processing/threshold.py` | `cv2.threshold` Otsu |
| `invert_image` | `cupy_processing/invert.py` | `255 - img` |
| `morph_fill` | `cupy_processing/morph.py` | `cv2.morphologyEx` |
| `crop_to_rectangle`, `crop_edges` | `cupy_processing/crop.py` | NumPy slicing |
| DocTR predictor | `ocr/doctr_support.py` | Tesseract |

### New GPU functions required (still owed to pd-book-tools)

#### `find_edges_gpu`

**File:** `pd_book_tools/image_processing/cupy_processing/edge_finding.py`
**CPU reference:** `cv2_processing/edge_finding.py`

Direct CuPy port of the CPU algorithm with one substitution:

| CPU | GPU |
|---|---|
| `np.sum(img, axis=0)` | `cp.sum(img, axis=0)` |
| `np.sum(img, axis=1)` | `cp.sum(img, axis=1)` |
| `np.convolve(arr, kernel, mode="same")` | `cupyx.scipy.ndimage.convolve1d(arr, kernel, mode="nearest")` |
| `np.where(arr >= threshold)[0]` | `cp.where(arr >= threshold)[0]` |
| Return `int` | `int(cp_scalar)` |

`cupyx.scipy.ndimage.convolve1d` with `mode="nearest"` matches NumPy's `"same"`
boundary behaviour.

```python
def find_edges_gpu(
    img_cp: "cp.ndarray",            # 2-D uint8, inverted (content=255, bg=0)
    fuzzy_pct: float = 0.02,
    pixel_count_columns: int = 150,
    pixel_count_rows: int = 75,
    fuzzy_px_w_override: int | None = None,
    fuzzy_px_h_override: int | None = None,
) -> tuple[int, int, int, int]:
    """Returns (minX, maxX, minY, maxY)."""
```

CPU-array convenience wrapper `np_uint8_find_edges(img, **kwargs)` transfers
to GPU, runs `find_edges_gpu`, returns the tuple.

#### `auto_deskew_gpu`

**File:** `pd_book_tools/image_processing/cupy_processing/deskew.py`
**CPU reference:** `cv2_processing/perspective_adjustment.py`

Two parts:

**(A) Angle detection.** Uses `find_edges_gpu` with `fuzzy_pct=0,
pixel_count_columns=1, pixel_count_rows=1` for tight content bounds. The
"find leftmost column with any content" loop becomes a single
`cp.where(col_sums > 0)[0]`. Right-triangle math is identical.

**(B) Image rotation.** Uses `cupyx.scipy.ndimage.affine_transform`. The
`affine_transform` API takes the **inverse** mapping: for a CW rotation of α
degrees, pass the CCW rotation matrix as `matrix` argument:

```
matrix = [[ cos α, -sin α ],
          [ sin α,  cos α ]]    # (row, col) order
```

New canvas size:
```python
abs_cos = abs(math.cos(alpha))
abs_sin = abs(math.sin(alpha))
new_h = int(h * abs_cos + w * abs_sin)
new_w = int(h * abs_sin + w * abs_cos)
```

Offset (rotate around image centre, place result in new canvas centre):
```python
cy, cx         = h / 2.0, w / 2.0
new_cy, new_cx = new_h / 2.0, new_w / 2.0
offset = [
    cy - cos_a * new_cy + sin_a * new_cx,
    cx - sin_a * new_cy - cos_a * new_cx,
]
```

Border fill = 0 (matches `cv2.warpAffine(borderValue=(0,0,0))`).

```python
def auto_deskew_gpu(
    img_cp: "cp.ndarray",
    pct: float = 0.30,
) -> tuple["cp.ndarray", "cp.ndarray", "cp.ndarray"]:
    """Returns (deskewed, top_slice_used, bottom_slice_used)."""
```

CPU-array wrapper `np_uint8_auto_deskew(img, pct=0.30)` returns NumPy.

#### Tests

`@pytest.mark.gpu` for both functions; each runs the GPU version against the
CPU reference on the same image and asserts bounding boxes within ±2 pixels
and rotation angles within ±0.1°.

---

## Backend 2 — `mps` (Apple Silicon)

Auto-selected on macOS arm64 when CUDA is not available. PyTorch's MPS backend
accelerates DocTR; image processing in Step 4 runs on CPU (CuPy is
NVIDIA-only). The pipeline reuses the `cpu` dispatch table for image
processing and routes DocTR through `device="mps"`:

```python
import torch

def get_doctr_device() -> str:
    if torch.cuda.is_available():
        return "cuda"
    if torch.backends.mps.is_available():
        return "mps"
    return "cpu"
```

Performance is dominated by Step 7 (OCR), so MPS gets most of the GPU win
on Apple Silicon despite Step 4 staying on CPU. A 400-page book on M2/M3
takes ~25 minutes total (cv2 grayscale ~3 s/page + MPS DocTR ~2 s/page).

No special install path — Apple Silicon users run the same `install.sh`; it
detects `arm64`/`Darwin` and skips the `--extra-index-url` (default PyTorch
wheel already includes MPS).

---

## Backend 3 — `cpu` (no GPU)

Auto-selected when `gpu_available()` returns `False` **and** the platform is
not Apple Silicon. The dispatch table in `core/pipeline/_dispatch.py` (above)
imports the cv2 functions instead of the CuPy functions.

The pipeline runs end-to-end without code changes. Performance characteristics:

| Step | CPU per page | Local CUDA per page |
|---|---|---|
| Grayscale (colorToGray) | ~30 s (GEGL) or ~1 s (cv2) | <1 s |
| Threshold (Otsu) | ~0.1 s | <0.05 s |
| find_edges | ~0.05 s | <0.01 s |
| auto_deskew | ~0.7 s | <0.15 s |
| morph_fill | ~0.3 s | <0.05 s |
| **Step 4 total** | **~30 s** if GEGL, **~3 s** if cv2 | **~2 s** |
| Step 7 OCR (DocTR) | ~5 s | ~1 s |

Switching from GEGL to cv2 grayscale brings CPU mode within an order of
magnitude of GPU mode. A 400-page book takes ~30 minutes of CPU compute end
to end (3 s × 400 + OCR), which is a tolerable overnight job for a personal
install.

The UI shows "CPU mode" prominently in the project header so the user
understands the timeline.

---

## Backend 4 — `modal` (serverless)

Used in **managed mode** (default) and as an opt-in in local/self-hosted for
users without a GPU.

### Modal function definitions

```python
# adapters/gpu/modal_backend.py
import modal

app = modal.App("pgdp-prep-gpu")

image = (
    modal.Image.debian_slim(python_version="3.13")
    .pip_install_from_pyproject("pyproject.toml")    # installs pgdp-prep + pd-book-tools
    .env({"CUDA_VISIBLE_DEVICES": "0"})
)

model_volume = modal.Volume.from_name("pd-ml-models", create_if_missing=False)

@app.function(
    gpu="T4",
    image=image,
    volumes={"/opt/pd-ml-models": model_volume},
    timeout=300,
    retries=1,
    container_idle_timeout=300,    # stay warm 5 min after last call
)
def process_page_remote(req: dict) -> dict:
    from pd_prep_for_pgdp.core.pipeline import run_page_pipeline
    from pd_prep_for_pgdp.api.gpu.schemas import ProcessPageRequest
    return run_page_pipeline(ProcessPageRequest(**req)).model_dump()

@app.function(gpu="T4", image=image, volumes={"/opt/pd-ml-models": model_volume},
              timeout=600, container_idle_timeout=300)
def run_ocr_remote(req: dict) -> dict:
    from pd_prep_for_pgdp.core.ocr import run_ocr_page
    from pd_prep_for_pgdp.api.gpu.schemas import OcrPageRequest
    return run_ocr_page(OcrPageRequest(**req)).model_dump()

@app.function(gpu="T4", image=image, volumes={"/opt/pd-ml-models": model_volume},
              timeout=1800, container_idle_timeout=600)
def run_batch_remote(items: list[dict]) -> list[dict]:
    """Batch entry point — all queued work for one dispatcher flush window.

    The 5-min flush window in managed mode collects pages here, then this
    single Modal invocation processes them with one cold start instead of
    paying it per page.
    """
    from pd_prep_for_pgdp.core.pipeline import run_batch_pipeline
    return [r.model_dump() for r in run_batch_pipeline(items)]
```

The Modal function imports `core.pipeline` directly. Modal's image build mounts
the same Python package, so the worker runs the **identical pipeline code** as
the local install — there is no parallel implementation.

### `ModalGPUBackend`

```python
# adapters/gpu/modal_backend.py
class ModalGPUBackend:
    def __init__(self):
        self._process_page = modal.Function.lookup("pgdp-prep-gpu", "process_page_remote")
        self._run_ocr      = modal.Function.lookup("pgdp-prep-gpu", "run_ocr_remote")
        self._run_batch    = modal.Function.lookup("pgdp-prep-gpu", "run_batch_remote")

    async def process_page(self, req: ProcessPageRequest) -> ProcessPageResponse:
        result = await self._process_page.remote.aio(req.model_dump())
        return ProcessPageResponse(**result)

    async def run_ocr(self, req: OcrPageRequest) -> OcrPageResponse:
        result = await self._run_ocr.remote.aio(req.model_dump())
        return OcrPageResponse(**result)

    async def run_batch(self, items: list[BatchJobItem]) -> list[BatchJobResult]:
        results = await self._run_batch.remote.aio([i.model_dump() for i in items])
        return [BatchJobResult(**r) for r in results]
```

### Model weights on Modal Volume

Fine-tuned DocTR `.pt` files are uploaded once:

```bash
modal volume create pd-ml-models
modal volume put pd-ml-models ~/.local/share/pd-ml-models/ /
```

Mounted at `/opt/pd-ml-models` in every function. `DOCTR_CACHE_DIR` env var
points pd-book-tools at this path. Updating weights is `modal volume put`
again — no container rebuild.

### Cold start

| Path | Latency |
|---|---|
| First call after deploy | 10–15 s (image pull + GPU init) |
| First call after idle (>5 min) | 5–8 s (container reload) |
| Warm call | 0.5–1.5 s plus actual compute |

The API surfaces cold-start to the frontend via `503 Retry-After: 15`. The
UI shows "GPU warming up…" with exponential back-off polling.

---

## Backend 5 — `shared_container`

For a managed deployment with sustained traffic that justifies a long-running
GPU. A single ECS EC2 task on `g4dn.xlarge` runs `pgdp-prep` with
`PGDP_MODE=gpu_worker_only` — no UI, no project DB access, just `/api/gpu/*`
endpoints. The frontend Fargate task dispatches via HTTP:

```python
# adapters/gpu/shared_container.py
class SharedContainerGPUBackend:
    def __init__(self, base_url: str, api_key: str):
        self._client = httpx.AsyncClient(
            base_url=base_url,
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=300.0,
        )

    async def process_page(self, req: ProcessPageRequest) -> ProcessPageResponse:
        r = await self._client.post("/api/gpu/process-page", json=req.model_dump())
        r.raise_for_status()
        return ProcessPageResponse(**r.json())

    async def run_batch(self, items: list[BatchJobItem]) -> list[BatchJobResult]:
        r = await self._client.post("/api/gpu/_internal/batch",
                                     json=[i.model_dump() for i in items])
        return [BatchJobResult(**x) for x in r.json()]
```

Tenants share the GPU but have isolated work queues; per-tenant API keys carry
a tenant-id claim used for fairness weighting in the worker's queue.

This backend is **opt-in**: Modal is the default because it has zero idle
cost. Switch when total GPU minutes per week exceed ~25 hours.

---

## Why batching matters

DocTR achieves 5–10× higher throughput when processing a batch of page images
in one forward pass. CuPy JIT kernels also warm up on the first call and stay
warm only while the CUDA context is alive. Routing all GPU work through a
single process with an in-memory queue maximises reuse.

In **local/self-hosted modes** with `local` GPU backend: a single FastAPI
process, single uvicorn worker, single-threaded GPU executor. A small priority
queue (200 ms collection window) batches concurrent requests. See
`core/queue/single_executor.py`.

In **managed mode** with `modal` or `shared_container`: the in-memory queue
becomes a 5-minute `BatchDispatcher` (spec 09). Interactive requests bypass
the dispatcher; batch jobs queue up. The dispatcher fires one Modal
`run_batch_remote` invocation per flush, amortising cold start across all
queued pages.

---

## Memory management (local backend)

CuPy arrays stay on GPU for the entire Step 4 sub-pipeline (4f → 4n) for one
page. CPU array is fetched once at 4c and the final result returned to CPU at
4o. No repeated PCIe round trips.

Rough budget per page at 3000×5000 px:

- uint8 image: ~15 MB
- float32 intermediate: ~60 MB
- Two morph copies: ~120 MB
- Peak per page: ~200 MB

A 4 GB GPU comfortably handles one page at a time; 16 GB (T4) handles ~8 pages
in a DocTR batch.

---

## Performance targets

| Step | CPU (cv2) | MPS (Apple Silicon) | Local CUDA | Modal warm | Modal cold |
|---|---|---|---|---|---|
| Grayscale | ~1 s | ~1 s (CPU) | <1 s | ~1 s | (one cold start per batch) |
| Threshold | ~0.1 s | ~0.1 s (CPU) | <0.05 s | ~0.05 s | |
| find_edges | ~0.05 s | ~0.05 s (CPU) | <0.01 s | <0.01 s | |
| auto_deskew | ~0.7 s | ~0.7 s (CPU) | <0.15 s | <0.2 s | |
| morph_fill | ~0.3 s | ~0.3 s (CPU) | <0.05 s | <0.05 s | |
| **Step 4 total** | **~3 s** | **~3 s** | **~2 s** | **~2 s** | **+ ~10 s once** |
| Step 7 OCR (per page) | ~5 s | ~2 s | ~1 s | ~1 s | |
| **Step 7 OCR (8-page batch)** | ~40 s | ~12 s | ~3 s | ~3 s | |

For managed mode, the cold-start tax appears once per dispatcher flush. A
400-page book at 5-min flush cadence is one cold start total (the whole
batch fits in one `run_batch_remote` call at the configured timeout).

---

## File layout

```
src/pd_prep_for_pgdp/
├── core/                          ← mode-agnostic; same code on every backend
│   ├── pipeline/
│   │   ├── step4_proofing.py      ← run_page_pipeline (per-page Step 4)
│   │   ├── step6_ocr_crop.py
│   │   ├── step7_ocr.py
│   │   ├── step8_postprocess.py
│   │   └── step10_package.py
│   ├── ocr/
│   │   ├── doctr.py
│   │   └── tesseract.py
│   └── queue/
│       └── single_executor.py     ← in-process priority queue (local/self-hosted)
│
└── adapters/gpu/
    ├── local.py                   ← in-process CuPy + CUDA PyTorch
    ├── mps.py                     ← in-process cv2 + MPS PyTorch (Apple Silicon)
    ├── cpu.py                     ← in-process NumPy/cv2 + CPU PyTorch
    ├── modal_backend.py           ← function definitions + ModalGPUBackend client
    └── shared_container.py        ← HTTP client to GPU worker
```

Adding `find_edges_gpu` and `auto_deskew_gpu` to pd-book-tools:

```
pd-book-tools/pd_book_tools/image_processing/cupy_processing/
├── __init__.py                    ← export find_edges_gpu, auto_deskew_gpu
├── edge_finding.py                ← NEW
└── deskew.py                      ← NEW
```
