#!/bin/bash
# Pre-commit stub-drift check: skip unless dakota.environment is importable.

set -u

PY="${PYTHON:-python3}"

if ! "$PY" -c "import dakota.environment" >/dev/null 2>&1; then
    echo "stub-drift: skipped (dakota.environment not importable; run 'make test' env or install a wheel first)"
    exit 0
fi
if ! "$PY" -c "import pybind11_stubgen" >/dev/null 2>&1; then
    echo "stub-drift: skipped (pybind11-stubgen not installed)"
    exit 0
fi

cd "$(dirname "$0")/.."

OUT=$(mktemp -d)
trap 'rm -rf "$OUT"' EXIT
"$PY" -m pybind11_stubgen dakota.environment -o "$OUT" >/dev/null
"$PY" scripts/normalize_stubs.py "$OUT/dakota/environment/environment.pyi"

failed=0
for f in __init__.pyi environment.pyi; do
    if ! diff "$OUT/dakota/environment/$f" "stubs/dakota/environment/$f"; then
        echo "stub-drift: stubs/dakota/environment/$f is stale — run 'make stubs' (needs a built wheel) and stage the result."
        failed=1
    fi
done
exit $failed
