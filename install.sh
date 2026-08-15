#!/usr/bin/env bash
set -euo pipefail

echo "========================================="
echo " ADTC 2026 POS Agent — Base Installer"
echo "========================================="

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_ROOT"

echo
echo "[1/8] Checking operating system..."

if [ -f /etc/os-release ]; then
    . /etc/os-release
    echo "OS: ${PRETTY_NAME:-unknown}"

    if [[ "${VERSION_ID:-}" != "22.04" ]]; then
        echo "WARNING: This project targets Ubuntu 22.04 LTS."
        echo "Current version: ${VERSION_ID:-unknown}"
    fi
else
    echo "WARNING: /etc/os-release not found."
fi

echo
echo "[2/8] Checking Python..."

if ! command -v python3 >/dev/null 2>&1; then
    echo "ERROR: python3 is not installed."
    exit 1
fi

python3 --version

echo
echo "[3/8] Checking required system tools..."

for tool in git curl; do
    if ! command -v "$tool" >/dev/null 2>&1; then
        echo "ERROR: $tool is not installed."
        exit 1
    fi
done

echo "git:  $(git --version)"
echo "curl: $(curl --version | head -n 1)"

echo
echo "[4/8] Checking project files..."

if [ ! -f "requirements.txt" ]; then
    echo "ERROR: requirements.txt not found."
    exit 1
fi

if [ ! -d "vendor/wheels" ]; then
    echo "ERROR: vendor/wheels directory not found."
    exit 1
fi

WHEEL_COUNT=$(find vendor/wheels -type f -name "*.whl" | wc -l)

echo "requirements.txt: OK"
echo "vendor/wheels: OK"
echo "Vendored wheels: $WHEEL_COUNT"

if [ "$WHEEL_COUNT" -eq 0 ]; then
    echo "ERROR: No wheel files found in vendor/wheels."
    exit 1
fi

echo
echo "[5/8] Creating required project directories..."

mkdir -p \
    data \
    data/sessions \
    logs \
    models \
    debug \
    skills

chmod 700 data/sessions

echo "Project directories: OK"

echo
echo "[6/8] Creating Python virtual environment..."

if [ ! -d "venv" ]; then
    echo "Creating venv..."

    if command -v python3.11 >/dev/null 2>&1; then
        python3.11 -m venv venv
    else
        python3 -m venv venv
    fi
else
    echo "venv/ already exists — keeping existing environment."
fi

# shellcheck disable=SC1091
source venv/bin/activate

echo "Python executable: $(which python)"
python --version

echo
echo "[7/8] Installing dependencies from local wheels..."

python -m pip install \
    --no-index \
    --find-links="$PROJECT_ROOT/vendor/wheels" \
    -r "$PROJECT_ROOT/requirements.txt"

echo
echo "[8/8] Running installation verification..."

python - <<'PY'
import sys

print("Python executable:", sys.executable)
print("Python version:", sys.version.split()[0])

required = [
    "flask",
    "pydantic",
    "psutil",
    "PIL",
    "onnxruntime",
    "pyudev",
    "duckdb",
    "numpy",
]

for module in required:
    try:
        __import__(module)
        print(f"{module}: OK")
    except Exception as exc:
        print(f"{module}: FAILED")
        print(exc)
        raise

from src.database import Database
from src.swahili_agreement import is_covered, noun_class_for

print("database.py import: OK")
print("swahili_agreement.py import: OK")

print()
print("=========================================")
print(" Base installation verification: PASSED")
print("=========================================")
PY

echo
echo "========================================="
echo " ADTC 2026 base installation complete."
echo "========================================="
echo
echo "Environment:"
echo "  $(which python)"
echo
echo "Next major step:"
echo "  llama-cpp-python compile/install"
echo
echo "That step is intentionally NOT included here."
echo "It will be handled separately during the model/runtime stage."
