# pd-prep-for-pgdp — Overview

## Purpose

A web application that converts a folder or zip of scanned book images (e.g.
from Internet Archive) into a PGDP-ready submission package: standard proofing
images, OCR text files, and a zip ready for upload.

Designed for two audiences from one codebase:

- **A solo proofer on a laptop** — one-line `curl … install.sh | sh` (same
  pattern as `pd-ocr-cli`). The installer detects NVIDIA CUDA via `nvidia-smi`
  and picks the matching PyTorch wheel; Apple Silicon picks up MPS for free;
  CPU-only systems install a pure-CPU build. `pgdp-prep` then opens a browser
  tab. No AWS, no Docker, no PyPI publish step (installs from the latest
  GitHub tag via `uv tool install`).
- **A hosted offering** — same wheel runs in a CPU-only Fargate container that
  defers all GPU work to Modal (or a shared GPU worker), batching most
  GPU-shaped operations on a configurable schedule (default every 5 minutes)
  to minimise cold starts and keep idle cost near zero.

The same Python pipeline runs in both. The only thing that changes between
modes is which adapter is wired in for storage, database, auth, GPU dispatch,
and batch scheduling.

---

## Deployment Shapes

Three shapes, one codebase. Spec 09 has the full breakdown.

| | Local | Self-hosted | Managed |
|---|---|---|---|
| Target user | Solo proofer | Small team | Hosted offering |
| Install | `curl … install.sh | sh` (uv tool install from GitHub tag) | systemd unit on a VM | ECS Fargate task |
| Storage | Filesystem | Filesystem or S3 | S3 |
| Database | SQLite | SQLite or Postgres | Postgres / Aurora |
| GPU | Local CUDA / MPS / CPU | Local CUDA / Modal | Modal / shared GPU container |
| Auth | None | API key | JWT (Cognito/Auth0) |
| Batch dispatch | Immediate | Immediate | 5-min flush (configurable) |
| AWS required | No | No | Yes |
| Idle cost | $0 | One VM | ~$10–15/month + GPU usage |

Mode is selected at startup by env vars. There is no "local build" vs "cloud
build" — the same wheel ships everywhere.

---

## Architecture

The entire app is a **single Python process** built around FastAPI:

```
┌──────────────────────────────────────────────────────────────────────┐
│  Browser — React SPA                                                 │
│  Vite-built bundle, served by the same FastAPI process               │
│  Konva canvas · TanStack Query · Zustand · shadcn/ui                 │
└─────────────────────────────────┬────────────────────────────────────┘
                                  │ HTTP/SSE
                                  ▼
┌──────────────────────────────────────────────────────────────────────┐
│  pgdp-prep (FastAPI + uvicorn) — single process                      │
│                                                                      │
│   /                  static SPA bundle (from package resources)      │
│   /api/data/*        project + page CRUD, presigned URLs, jobs       │
│   /api/gpu/*         image processing + OCR (sync or batched)        │
│   /cdn/*             local image files (filesystem mode only)        │
│   /api/auth/*        identity (none / api-key / JWT verify)          │
│                                                                      │
│   ┌─ core/                                                           │
│   │   resolve_page_config · pipeline · ocr · packaging               │
│   │   (mode-agnostic — used everywhere)                              │
│   │                                                                  │
│   ├─ adapters/                                                       │
│   │   storage  · database · auth · gpu                               │
│   │   (one chosen per process; selected by env vars at startup)      │
│   │                                                                  │
│   └─ dispatcher/                                                     │
│       immediate (local/self-hosted) · batched (managed, 5-min flush) │
└─────────────────────┬────────────────────────────┬───────────────────┘
                      │ IStorage                   │ GPUBackend
                      ▼                            ▼
              ┌───────────────┐          ┌──────────────────┐
              │ Filesystem    │          │ Local CUDA       │
              │ or S3         │          │ CPU fallback     │
              └───────────────┘          │ Modal serverless │
                                         │ Shared container │
                                         └──────────────────┘
```

**Data API and GPU API are routes on the same FastAPI app**, not separate
services. (An earlier draft of this spec had a Hono Lambda data API and a
separate FastAPI GPU API. That is now collapsed — see "Why one process" below.)

In **managed mode**, the same FastAPI process runs in a small CPU-only Fargate
container; the `/api/gpu/*` routes dispatch GPU work to Modal (or a shared GPU
container) instead of running pd-book-tools in-process. Workbench/interactive
GPU calls fire immediately; long batch jobs queue up and flush every 5 minutes
to amortise cold starts.

---

## Why one process

| Property | Two-stack design (Hono + FastAPI) | One-stack design (FastAPI only) |
|---|---|---|
| Languages | TypeScript + Python | Python |
| Deploy units | 2 (Lambda zip, EC2 systemd) | 1 (wheel or container) |
| Local install for a non-AWS user | `npm` + `uv` + 3 .env files + 3 terminals | `pip install pgdp-prep` |
| Cold-start (Lambda data API) | ~200 ms | n/a — Fargate stays warm |
| Type sharing | `packages/api-types` workspace | OpenAPI codegen → TS |
| Frontend distribution | Separate static bucket | Bundled into the wheel |

The 200 ms cold-start advantage Hono had on Lambda doesn't matter when the
CPU-only Fargate container is always-on. Local mode never sees Lambda at all.

---

## Tech Stack

| Layer | Choice |
|---|---|
| Frontend | React 19 + Vite + TypeScript |
| Canvas | react-konva |
| Frontend state | Zustand (UI) + TanStack Query v5 (server state) |
| Styling | Tailwind + shadcn/ui |
| Routing | React Router v7 |
| Backend | FastAPI (Python 3.13) + uvicorn |
| Pipeline | pd-book-tools (CuPy / cv2 / DocTR / Tesseract) |
| Type sharing | OpenAPI spec generated by FastAPI → `openapi-typescript` codegen |
| Build | hatchling + hatch-vcs (version from git tags); static frontend included via `force-include` |
| Distribution | `uv tool install git+https://…@<tag>` — no PyPI publish; install.sh resolves the latest tag from GitHub |

`pd-book-tools` is the shared library powering image processing and OCR. It is
used by `pd-ocr-cli`, `pd-ocr-labeler`, `pd-ocr-trainer`, and this app.

---

## Configuration

Three resolution tiers (full detail in spec 01):

| Layer | Storage | Edited from |
|---|---|---|
| `SystemDefaults` | `~/.config/pgdp-prep/defaults.json` (local) / `system_defaults` row (hosted) | Settings page |
| `ProjectConfig` | `projects/<id>/project.json` | Configure page Book Settings |
| `PageRecord` | `projects/<id>/pages/<idx0>.json` (one file per page) | Page tagger + PageWorkbench |

A single resolver (`resolve_page_config`) merges all three into a flat
`ResolvedPageConfig` consumed by the pipeline. Pipeline steps never look at
the raw config layers.

---

## GPU Backend Abstraction

```python
class GPUBackend(Protocol):
    async def process_page(self, req: ProcessPageRequest) -> ProcessPageResponse: ...
    async def run_ocr(self, req: OcrPageRequest) -> OcrPageResponse: ...
    async def run_batch(self, items: list[BatchJobItem]) -> list[BatchJobResult]: ...
```

| Backend | Runtime |
|---|---|
| `local` | In-process CuPy + DocTR (CUDA required) |
| `cpu` | NumPy + cv2 + CPU PyTorch DocTR; auto-selected when no CUDA |
| `modal` | Dispatches each call to a Modal function (cold-start ~10–15 s, $0.40/GPU-h T4) |
| `shared_container` | HTTP client to a long-running GPU ECS task shared across tenants |

CPU mode is **first-class**, not a degraded experience. A 400-page book takes
~3 hours of CPU compute on a modern laptop; the UI surfaces "CPU mode — slow"
without blocking any feature.

---

## Pipeline as Background Jobs

Long operations (page processing, batch OCR, packaging) are submitted as jobs.
The API returns a `job_id` immediately; the frontend subscribes to
`GET /api/gpu/jobs/{job_id}/events` (SSE) for live progress.

In **managed mode**, batch jobs go through the `BatchDispatcher` (5-min
default flush window). Interactive operations (single-page workbench preview,
text-review re-OCR) bypass the dispatcher and fire immediately, accepting
the Modal cold-start tax when it happens.

---

## Key Flows

### New project from zip

1. `POST /api/data/projects` → server creates project record + project.json
2. Browser uploads zip (presigned PUT in hosted mode; direct upload in local mode)
3. `POST /api/gpu/ingest` → server extracts zip, generates thumbnails, writes
   page records → returns `job_id`
4. Browser polls job until complete; page tagger becomes available

### Per-page live preview (PageWorkbench)

1. User adjusts a parameter in the workbench
2. `POST /api/gpu/process-page` with overrides → GPU backend processes page,
   stores result, returns URL → canvas updates
3. In managed mode the first call may show "GPU warming up" (~10–15 s);
   subsequent calls within the warm window are fast

### Batch pipeline

1. `POST /api/gpu/jobs` with `{type: "batch_process_pages", pages: […]}`
2. In local/self-hosted: starts immediately
3. In managed: queues for the next dispatcher flush (≤5 min)
4. SSE stream pushes progress events to the UI

---

## Pipeline flow

```
[Ingest + Thumbnails]
        │
        ▼
[Configure / Tag pages]   ←→   [PageWorkbench (any page, any time)]
        │
        ▼
[Step 4 — Proofing image pipeline]
        │
        ▼
[Step 4.5 — Illustration extraction]   (per configured region; spec 05)
        │
        ▼
[Step 5 — Inspect proofing images]
        │
        ▼
[Step 6 — Crop for OCR]
        │
        ▼
[Step 7 — OCR]
        │
        ▼
[Step 8 — Text post-processing]
        │
        ▼
[Step 9 — Text review]
        │
        ▼
[Step 10 — Package / Build zip]
```

---

## Scope

**In scope:** all 10 pipeline steps, PageWorkbench with live GPU preview,
visual page tagger with per-page config, split editor, illustration extraction,
PGDP package assembly.

**Out of scope:** PGDP project submission (still a manual step on
distributedproofreaders.org), DocTR model training (lives in `pd-ocr-trainer`).

**Stretch goal — multi-user:** the architecture does not block it. `Project`
and `Job` carry `owner_id` (defaults to `"default"` in single-user mode); auth
middleware always resolves a user identity from the token; `GET /projects`
filters by `owner_id`. Swap the auth adapter from `none` to `jwt` and it works.

---

## Relationship to Existing Projects

`pd-book-tools` is the shared Python library used here, in `pd-ocr-cli`,
`pd-ocr-labeler`, and `pd-ocr-trainer`. They all consume the same OCR/geometry
primitives; this app additionally consumes `core/` (this repo's pipeline
orchestration on top of pd-book-tools).
