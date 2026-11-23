#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

is_conda_python() {
    local py="$1"
    "$py" - <<'PY' >/dev/null 2>&1
import sys
from pathlib import Path
prefix = Path(sys.prefix)
exe = Path(sys.executable).as_posix().casefold()
is_conda = (prefix / "conda-meta").exists() or "conda" in exe or "anaconda" in exe
raise SystemExit(1 if is_conda else 0)
PY
}

resolve_build_python() {
    local candidates=()
    if [[ -n "${PARQSCAN_BUILD_PYTHON:-}" ]]; then
        candidates+=("$PARQSCAN_BUILD_PYTHON")
    fi
    for candidate in \
        "/opt/homebrew/bin/python3.12" \
        "/usr/local/bin/python3.12" \
        "/Library/Frameworks/Python.framework/Versions/3.12/bin/python3" \
        "$(command -v python3.12 || true)" \
        "$(command -v python3 || true)"; do
        [[ -n "$candidate" && -x "$candidate" ]] && candidates+=("$candidate")
    done

    for py in "${candidates[@]}"; do
        if is_conda_python "$py"; then
            echo "$py"
            return 0
        fi
    done

    echo "ERROR: No non-Conda Python 3 was found for macOS release builds." >&2
    echo "Install Python 3.12 via Homebrew (brew install python@3.12) or python.org, or set PARQSCAN_BUILD_PYTHON." >&2
    return 1
}

ARCH="$(uname -m)"
if [[ "$ARCH" != "arm64" && "${PARQSCAN_ALLOW_NON_ARM64:-0}" != "1" ]]; then
    echo "WARNING: Building on $ARCH instead of Apple Silicon (arm64)." >&2
fi

BASE_PYTHON="$(resolve_build_python)"
VENV_DIR="$ROOT_DIR/.build-venv"
VENV_PYTHON="$VENV_DIR/bin/python"

if [[ -d "$VENV_DIR" ]]; then
    if [[ -f "$VENV_DIR/pyvenv.cfg" ]] && grep -qiE "conda|anaconda" "$VENV_DIR/pyvenv.cfg"; then
        echo "Removing Conda-based .build-venv..."
        rm -rf "$VENV_DIR"
    fi
fi

if [[ ! -x "$VENV_PYTHON" ]]; then
    "$BASE_PYTHON" -m venv "$VENV_DIR"
fi

"$VENV_PYTHON" -m pip install --upgrade pip
"$VENV_PYTHON" -m pip install -r requirements.txt pyinstaller

export PARQSCAN_STRICT_BUILD="1"
export PARQSCAN_TARGET_ARCH="${PARQSCAN_TARGET_ARCH:-$ARCH}"
"$VENV_PYTHON" build.py --installer --package-format dmg "$@"
