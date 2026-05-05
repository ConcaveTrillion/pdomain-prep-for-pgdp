# pgdp-prep installer (Windows PowerShell)
#
# Usage:
#   irm https://raw.githubusercontent.com/ConcaveTrillion/pd-prep-for-pgdp/main/install.ps1 | iex

$ErrorActionPreference = "Stop"

function Test-Command($name) {
    Get-Command $name -ErrorAction SilentlyContinue | ForEach-Object { return $true }
    return $false
}

# 1. Install uv if missing
if (-not (Test-Command "uv")) {
    Write-Host "uv not found — installing uv..."
    Invoke-RestMethod -Uri "https://astral.sh/uv/install.ps1" -UseBasicParsing | Invoke-Expression
    $env:Path = "$HOME\.local\bin;" + $env:Path
}

# 2. Detect NVIDIA GPU
$extraIndex = ""
$extras = ""
if (Test-Command "nvidia-smi") {
    try {
        $smiOutput = & nvidia-smi 2>$null | Out-String
        if ($smiOutput -match 'CUDA Version:\s+([0-9]+)\.([0-9]+)') {
            $cudaTag = "cu$($Matches[1])$($Matches[2])"
            $extraIndex = "https://download.pytorch.org/whl/$cudaTag"
            $extras = "[cuda]"
            Write-Host "Detected CUDA $($Matches[1]).$($Matches[2]) — installing with $cudaTag + CuPy."
        }
    } catch {
        Write-Host "nvidia-smi failed — falling back to CPU."
    }
} else {
    Write-Host "No NVIDIA GPU detected — installing CPU-only build."
}

# 3. Resolve latest tag
$repo = "ConcaveTrillion/pd-prep-for-pgdp"
$installRef = "git+https://github.com/$repo"
try {
    $tags = Invoke-RestMethod "https://api.github.com/repos/$repo/tags"
    if ($tags -and $tags[0].name) {
        $installRef = "git+https://github.com/$repo@$($tags[0].name)"
        Write-Host "Installing pgdp-prep $($tags[0].name)..."
    }
} catch {
    Write-Host "Could not resolve latest tag — installing from main."
}

# 4. uv tool install
$installTarget = "$installRef$extras"
if ($extraIndex) {
    & uv tool install --reinstall $installTarget --extra-index-url $extraIndex
} else {
    & uv tool install --reinstall $installTarget
}

Write-Host ""
Write-Host "Done! Run: pgdp-prep"
