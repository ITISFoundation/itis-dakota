#!/bin/bash
# Keep requirements.txt (the committed lock GitHub's dependency graph and
# dependency-review parse) in sync with pyproject.toml. Compares resolved
# pins only, so the uv header/command line never causes false drift.

set -euo pipefail

cd "$(dirname "$0")/.."

if ! command -v uv >/dev/null 2>&1; then
    echo "requirements-lock: skipped (uv not installed)"
    exit 0
fi

OUT=$(mktemp)
trap 'rm -f "$OUT"' EXIT
uv pip compile --quiet pyproject.toml --python-version 3.12 -o "$OUT" >/dev/null

strip() { grep -v '^#' "$1" | sed '/^$/d'; }

if ! diff <(strip "$OUT") <(strip requirements.txt) >/dev/null; then
    echo "requirements-lock: requirements.txt is stale — run 'make lock' and commit the result."
    diff <(strip "$OUT") <(strip requirements.txt) || true
    exit 1
fi
