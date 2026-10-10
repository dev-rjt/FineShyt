#!/usr/bin/env bash
set -euo pipefail

PYTHON_BIN="${PYTHON_BIN:-python3}"

"$PYTHON_BIN" src/data/download_public_sources.py
"$PYTHON_BIN" src/data/build_dataset.py --customers 5000 --seed 42
"$PYTHON_BIN" src/data/validate_dataset.py
