"""HuggingFace download + model resolution helpers.

Lifted from `pd-ocr-cli/pd_ocr_cli/_hf_download.py` + `_hf_models.py` so
this app uses the same canonical OCR + layout model resolution as the CLI.
Both apps share `pd-book-tools` as the inference primitive — only this
"how do we find the .pt files" layer is duplicated.
"""

from __future__ import annotations

import contextlib
import logging
from pathlib import Path

DEFAULT_HF_REPO = "CT2534/pd-ocr-models"
DEFAULT_DET_FILENAME = "detection/pd-all-detection-model-finetuned.pt"
DEFAULT_RECO_FILENAME = "recognition/pd-all-recognition-model-finetuned.pt"

# Sidecars the trainer writes alongside each `.pt` checkpoint. pd-book-tools
# prefers these to heuristic detection when present.
OCR_MODEL_SIDECARS = (".arch", ".vocab")

LAYOUT_MODEL_FILES = ("config.json", "preprocessor_config.json", "model.safetensors")


@contextlib.contextmanager
def _suppress_hf_unauth_warning():
    """Suppress HF Hub's "unauthenticated requests" advisory only.

    Public models intentionally support anonymous downloads; the warning is
    noisy for the common path. Other HF warnings still surface.
    """

    class _Filter(logging.Filter):
        def filter(self, record: logging.LogRecord) -> bool:
            msg = record.getMessage().lower()
            return not ("unauthenticated requests" in msg and "hf hub" in msg)

    logger = logging.getLogger("huggingface_hub.utils._http")
    f = _Filter()
    logger.addFilter(f)
    try:
        yield
    finally:
        logger.removeFilter(f)


def hf_download(
    repo_id: str,
    filename: str,
    revision: str | None = None,
    sidecars: tuple[str, ...] = (),
) -> Path:
    """Download `filename` from `repo_id` and return the cached local path.

    Optional `sidecars` (e.g. `(".arch", ".vocab")`) are best-effort: missing
    sidecars are silently skipped.
    """
    from huggingface_hub import hf_hub_download

    try:
        from huggingface_hub import _CACHED_NO_EXIST, try_to_load_from_cache

        cached = try_to_load_from_cache(repo_id=repo_id, filename=filename, revision=revision)
        already_cached = cached is not None and cached is not _CACHED_NO_EXIST
    except Exception:
        already_cached = False

    if not already_cached:
        log = logging.getLogger(__name__)
        log.info("Downloading %s from %s (revision=%s)", filename, repo_id, revision or "latest")

    with _suppress_hf_unauth_warning():
        local = hf_hub_download(repo_id=repo_id, filename=filename, revision=revision)

    if sidecars:
        try:
            from huggingface_hub.utils import EntryNotFoundError as _HFNotFound
        except ImportError:
            _HFNotFound = Exception  # type: ignore[assignment,misc]
        for ext in sidecars:
            sidecar = filename.rsplit(".", 1)[0] + ext
            try:
                with _suppress_hf_unauth_warning():
                    hf_hub_download(repo_id=repo_id, filename=sidecar, revision=revision)
            except _HFNotFound:
                pass

    return Path(local)


# ─── OCR detection + recognition ─────────────────────────────────────────────


def resolve_ocr_models(
    *,
    repo: str = DEFAULT_HF_REPO,
    revision: str | None = None,
    det_filename: str = DEFAULT_DET_FILENAME,
    reco_filename: str = DEFAULT_RECO_FILENAME,
    detection_path: Path | None = None,
    recognition_path: Path | None = None,
) -> tuple[Path, Path]:
    """Return (det_path, reco_path) — local paths take precedence over HF Hub.

    Either both `detection_path` and `recognition_path` are passed (local
    files), or both are omitted (download from HF Hub).
    """
    if bool(detection_path) != bool(recognition_path):
        raise ValueError(
            "detection_path and recognition_path must both be set or both omitted"
        )
    if detection_path and recognition_path:
        if not detection_path.is_file():
            raise FileNotFoundError(f"detection model not found: {detection_path}")
        if not recognition_path.is_file():
            raise FileNotFoundError(f"recognition model not found: {recognition_path}")
        return detection_path, recognition_path

    det = hf_download(repo, det_filename, revision, sidecars=OCR_MODEL_SIDECARS)
    reco = hf_download(repo, reco_filename, revision, sidecars=OCR_MODEL_SIDECARS)
    return det, reco


# ─── Layout model ────────────────────────────────────────────────────────────


def resolve_layout_source(
    layout_model: str,
    layout_checkpoint: str | None = None,
) -> tuple[str | None, str | None, str]:
    """Return (repo, revision, descriptor) for the configured layout model.

    `repo` and `revision` are None for backends that don't pull from HF Hub
    (`none`, `contour`, or a local checkpoint path). The descriptor is a
    human-readable label.
    """
    if layout_model == "none":
        return (None, None, "")
    if layout_model == "contour":
        return (None, None, "contour (built-in)")

    # pp-doclayout-plus-l (or any HF-hosted layout model)
    if layout_checkpoint:
        ckpt = Path(layout_checkpoint)
        if ckpt.exists():
            return (None, None, str(ckpt))
        return (layout_checkpoint, None, f"{layout_checkpoint}@latest")

    from pd_book_tools.layout.adapters.pp_doclayout import PPDocLayoutPlusLDetector

    return (
        PPDocLayoutPlusLDetector.HF_REPO,
        PPDocLayoutPlusLDetector.HF_REVISION,
        f"{PPDocLayoutPlusLDetector.HF_REPO}@{(PPDocLayoutPlusLDetector.HF_REVISION or 'latest')[:8]}",
    )


def prefetch_layout_files(repo: str, revision: str | None) -> None:
    """Pre-download the HF transformers files so the later
    `from_pretrained()` call inside the adapter is a cache hit.
    """
    for fname in LAYOUT_MODEL_FILES:
        hf_download(repo, fname, revision)


def silence_transformers_load_chatter() -> None:
    """Disable transformers' verbose logging + in-memory weight progress bar."""
    try:
        from transformers.utils import logging as _hf_logging

        _hf_logging.set_verbosity_error()
        _hf_logging.disable_progress_bar()
    except Exception:
        pass
