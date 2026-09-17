#!/bin/bash
#
# Regenerate stubs/dakota/environment/{__init__.pyi,environment.pyi} from
# the compiled dakota.environment extension. Requires wheelhouse/*.whl to
# already exist (run `make wheel` first, or invoke via `make stubs`).

set -ex

cd "$(dirname "$0")/.."

STUBS_VENV=.venv-stubs
STUBS_DIR=stubs/dakota/environment

rm -rf "$STUBS_VENV"

WHEEL=$(ls wheelhouse/itis_dakota-*.whl | head -1)
PYTAG=$(echo "$WHEEL" | sed -E 's/.*-(cp[0-9]+)-.*\.whl/\1/')
PYVER=$(echo "$PYTAG" | sed -E 's/cp([0-9])([0-9]+)/\1.\2/')

echo "Generating stubs for Python $PYVER (wheel: $WHEEL)"

STUBGEN=pybind11-stubgen==2.5.5

if command -v uv >/dev/null 2>&1; then
	uv venv --python "$PYVER" "$STUBS_VENV"
	uv pip install --python "$STUBS_VENV/bin/python" numpy "$STUBGEN" "$WHEEL"
else
	"python$PYVER" -m venv "$STUBS_VENV"
	"$STUBS_VENV/bin/pip" install numpy "$STUBGEN" "$WHEEL"
fi

OUT=$(mktemp -d)
"$STUBS_VENV/bin/pybind11-stubgen" dakota.environment -o "$OUT"

mkdir -p "$STUBS_DIR"
cp "$OUT/dakota/environment/__init__.pyi" "$STUBS_DIR/__init__.pyi"
cp "$OUT/dakota/environment/environment.pyi" "$STUBS_DIR/environment.pyi"
touch "$STUBS_DIR/py.typed"

# Fixups shared with the CI stub-drift check (see
# .github/workflows/buildwheels.yml) so both apply identical normalization
# to the pybind11-stubgen output.
python3 scripts/normalize_stubs.py "$STUBS_DIR/environment.pyi"

rm -rf "$OUT" "$STUBS_VENV"

echo "Stubs written to $STUBS_DIR/__init__.pyi"
