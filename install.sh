#!/bin/sh
set -e

# Install pgdp-prep as a standalone tool using uv.
#
# Usage:
#   curl -sSL https://raw.githubusercontent.com/ConcaveTrillion/pd-prep-for-pgdp/main/install.sh | sh

# 1. Install uv if not already present
if ! command -v uv >/dev/null 2>&1; then
    echo "uv not found — installing uv..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    export PATH="$HOME/.local/bin:$PATH"
fi

EXTRA_INDEX=""
EXTRAS=""

# 2. Detect platform → pick PyTorch index
if command -v nvidia-smi >/dev/null 2>&1 && nvidia-smi >/dev/null 2>&1; then
    CUDA_VER=$(nvidia-smi 2>/dev/null | sed -n 's/.*CUDA Version: \([0-9]*\.[0-9]*\).*/\1/p' | head -1)
    if [ -n "$CUDA_VER" ]; then
        CUDA_TAG="cu$(echo "$CUDA_VER" | tr -d '.')"
        EXTRA_INDEX="https://download.pytorch.org/whl/${CUDA_TAG}"
        EXTRAS="[cuda]"
        echo "Detected CUDA ${CUDA_VER} — installing with ${CUDA_TAG} + CuPy."
    else
        echo "nvidia-smi found but could not detect CUDA version — falling back to CPU."
    fi
elif [ "$(uname)" = "Darwin" ] && [ "$(uname -m)" = "arm64" ]; then
    echo "Detected Apple Silicon — DocTR will use MPS automatically."
else
    echo "No GPU detected — installing CPU-only build."
fi

# 3. Resolve latest tag
REPO="ConcaveTrillion/pd-prep-for-pgdp"
LATEST_TAG=$(curl -sSf "https://api.github.com/repos/${REPO}/tags" 2>/dev/null \
    | grep '"name"' | head -1 | sed 's/.*"name": "\([^"]*\)".*/\1/') || true

if [ -n "$LATEST_TAG" ]; then
    INSTALL_REF="git+https://github.com/${REPO}@${LATEST_TAG}"
    echo "Installing pgdp-prep ${LATEST_TAG}..."
else
    INSTALL_REF="git+https://github.com/${REPO}"
    echo "Installing pgdp-prep (latest commit — could not resolve tag)..."
fi

# 4. uv tool install
if [ -n "$EXTRA_INDEX" ]; then
    uv tool install --reinstall "${INSTALL_REF}${EXTRAS}" --extra-index-url "$EXTRA_INDEX"
else
    uv tool install --reinstall "${INSTALL_REF}${EXTRAS}"
fi

echo ""
echo "Done! Run: pgdp-prep"
echo "If 'pgdp-prep' is not found, add uv's tool bin to your PATH:"
echo "  export PATH=\"\$HOME/.local/bin:\$PATH\""
