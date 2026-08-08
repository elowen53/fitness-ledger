#!/usr/bin/env bash
# macOS / Linux entry point for the fitness ledger CLI.
# Uses the bundled Python implementation (scripts/fitness.py), which mirrors
# scripts/fitness.ps1. Windows users keep using fitness.ps1.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON_BIN="${PYTHON_BIN:-python3}"

exec "$PYTHON_BIN" "$SCRIPT_DIR/fitness.py" "$@"
