"""Runtime configuration. Reads `PGDP_*` env vars (and a few others)."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

StorageBackend = Literal["filesystem", "s3"]
DatabaseKind = Literal["sqlite", "postgres"]
AuthMode = Literal["none", "apikey", "jwt"]
GpuBackend = Literal["local", "cpu", "mps", "modal", "shared_container"]


class Settings(BaseSettings):
    """One process-wide settings instance. Chosen at startup; never mutated."""

    model_config = SettingsConfigDict(
        env_prefix="PGDP_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ── Server ───────────────────────────────────────────────────────────────
    host: str = "127.0.0.1"
    port: int = 8765
    frontend_dev_url: str | None = None
    """When set, the SPA mount falls through to this Vite dev server."""

    # ── Data root ────────────────────────────────────────────────────────────
    data_root: Path = Field(default_factory=lambda: Path.home() / "pgdp-projects")
    doctr_cache_dir: Path = Field(
        default_factory=lambda: Path.home() / ".cache" / "pd-ml-models"
    )
    config_dir: Path = Field(
        default_factory=lambda: Path.home() / ".config" / "pgdp-prep"
    )

    # ── Storage adapter ──────────────────────────────────────────────────────
    storage_backend: StorageBackend = "filesystem"
    s3_data_bucket: str | None = None
    s3_cdn_base_url: str | None = None

    # ── Database adapter ─────────────────────────────────────────────────────
    database_url: str = ""
    """sqlite:///path or postgres://... — empty = derive sqlite path from data_root."""

    # ── Auth adapter ─────────────────────────────────────────────────────────
    auth_mode: AuthMode = "none"
    api_key: str | None = None
    jwt_issuer: str | None = None
    jwt_audience: str | None = None

    # ── GPU backend ──────────────────────────────────────────────────────────
    gpu_backend: GpuBackend | None = None
    """When None, auto-detect at startup (CUDA → local, mac arm64 → mps, else cpu)."""

    modal_token_id: str | None = None
    modal_token_secret: str | None = None
    shared_gpu_url: str | None = None
    shared_gpu_api_key: str | None = None

    # ── Dispatch cadence ─────────────────────────────────────────────────────
    dispatch_interval_seconds: int = 0
    """0 = immediate (local/self-hosted). 300 = managed-mode batch flush."""

    # ── Mode flag (for shared GPU worker container) ──────────────────────────
    mode: Literal["full", "gpu_worker_only"] = "full"

    @property
    def derived_database_url(self) -> str:
        if self.database_url:
            return self.database_url
        return f"sqlite:///{(self.data_root / 'state.db').as_posix()}"

    @property
    def cdn_enabled(self) -> bool:
        return self.storage_backend == "filesystem"
