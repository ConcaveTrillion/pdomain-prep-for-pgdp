# 06 — Deployment

Spec 09 lays out three shapes. This doc tracks what's actually shippable today
vs what still needs work.

## Local — `pgdp-prep`

**Status:** ✅ shippable.

```sh
curl -sSL https://raw.githubusercontent.com/ConcaveTrillion/pd-prep-for-pgdp/main/install.sh | sh
pgdp-prep
```

`install.sh` (mirrors `pd-ocr-cli/install.sh`):

1. Install `uv` if missing.
2. Detect NVIDIA via `nvidia-smi`; if found, set `EXTRA_INDEX` to the right
   PyTorch CUDA wheel index and add the `[cuda]` extra.
3. Resolve the latest GitHub tag from the `tags` API.
4. `uv tool install --reinstall git+https://github.com/.../pd-prep-for-pgdp[@tag][cuda]`.

Defaults at startup (no env vars set):

| Setting | Default |
|---|---|
| `host` / `port` | `127.0.0.1:8765` |
| `data_root` | `~/pgdp-projects` |
| `storage_backend` | `filesystem` |
| `database_url` | `sqlite:///~/pgdp-projects/state.db` |
| `auth_mode` | `none` |
| `gpu_backend` | auto-detect (`local` if cupy importable, else `mps` on macOS arm64, else `cpu`) |
| `dispatch_interval_seconds` | `0` (immediate) |

`__main__.py` opens a browser tab on start unless `--no-browser` is passed.

## Self-hosted

**Status:** ✅ shippable for filesystem + SQLite + apikey. Postgres is deferred.

Same wheel; flip env vars:

```sh
PGDP_HOST=0.0.0.0
PGDP_DATA_ROOT=/var/lib/pgdp
PGDP_AUTH_MODE=apikey
PGDP_API_KEY=...
# optional: PGDP_STORAGE_BACKEND=s3 + S3_DATA_BUCKET=...
# optional: PGDP_GPU_BACKEND=modal + MODAL_TOKEN_ID=... MODAL_TOKEN_SECRET=...
```

Recommended: systemd unit + Caddy/nginx for TLS. The team-of-five default
reads from one shared Postgres + one shared GPU box (or Modal for burst).

## Managed (Fargate + Modal)

**Status:** 🟡 scaffolded, not yet end-to-end.

What's working:

- `Dockerfile` builds a CPU-only Python 3.13 image with `[s3,postgres,modal,jwt]`
  extras. Frontend SPA copied in from a Node build stage. ~150 MB image.
- Bootstrap selects S3 + Postgres (when implemented) + JWT + Modal at
  startup based on env vars.
- `BatchDispatcher` flushes every 5 minutes by default; managed-mode jobs
  enter `scheduled` status until the next flush.
- `ModalBackend` looks up deployed Modal Functions by name and dispatches
  via `.remote.aio()`. Wire shape verified by 3 TDD tests against a fake
  `modal` module.

What still needs work:

- **`modal_app.py` function bodies** — `process_page` / `run_ocr` /
  `run_batch` raise `NotImplementedError`. The Modal-side container needs
  its own S3 IStorage so it can read source bytes + write outputs back.
  Roadmap item #1.
- **Postgres adapter** — schema exists in spec 08; the `IDatabase` impl is
  deferred (psycopg + SQLAlchemy not in this devcontainer's venv).
- **`.github/workflows/release.yml`** builds the container on tag push but
  doesn't push to ECR (the user's registry isn't configured).

Cost estimate (per spec 09): with 100 books/month, ~$70/month total. Modal
GPU charges are ~$2/book; rest is Fargate (~$10) + Aurora (~$45) + S3 (~$5).

## CI

`.github/workflows/release.yml` runs on push to main and on tag push:

| Job | When | What |
|---|---|---|
| `test` | every push | uv sync + ruff + pytest |
| `build-frontend` | every push | npm install + `vite build`; uploads `dist/` |
| `build-wheel` | every push (after test + build-frontend) | uv build with frontend bundled into the wheel |
| `build-container` | tag push only | docker build (no push wired up — user's ECR config) |

## Frontend bundling

Spec 09 — the SPA lives inside the Python wheel:

1. `vite build` writes to `frontend/dist/`.
2. CI copies that into `src/pd_prep_for_pgdp/static/`.
3. `pyproject.toml`'s `[tool.hatch.build.targets.wheel.force-include]`
   bundles it into the wheel under `pd_prep_for_pgdp/static/`.
4. At runtime `bootstrap._mount_static_frontend` mounts that directory at
   `/`. `index.html` loads `/env.js` first (FastAPI-served, see backend doc).

The dev workflow is different: `pgdp-prep --frontend-dev http://localhost:5173`
keeps the FastAPI process from mounting the static SPA, so Vite's dev server
on port 5173 owns `/` while FastAPI owns `/api/*` and `/cdn/*`.

## What's not deployed yet

- **Modal app deploy** — the user runs `modal deploy
  src/pd_prep_for_pgdp/adapters/gpu/modal_app.py` themselves; CI doesn't.
- **install.sh exercise** — we haven't actually run it in a clean shell to
  verify the curl-pipe-sh flow works end-to-end. Logged for the user.
- **Git remote** — repo isn't a git repo yet. `git init` + remote create
  is the user's call (decision logged in iteration 1).
