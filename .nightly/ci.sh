#!/usr/bin/env bash
set -euo pipefail

echo "=== Installing package ==="
pip install -e ".[dev]" --quiet

echo "=== Running tests ==="
python -m pytest tests/ -v

echo "=== Import check ==="
python -c "import webui; print('webui OK')"

echo "=== All checks passed ==="
