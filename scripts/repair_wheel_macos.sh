#!/bin/bash
# macOS wheel repair using delocate.
#
# Equivalent in spirit to scripts/repair_wheel.sh but for Mach-O binaries on
# macOS.
#
# IMPORTANT — py-build-cmake .data/platlib quirk:
#   py-build-cmake installs the extension module via
#       <dist>.data/platlib/dakota/environment/environment.so
#   When the wheel is installed, `<dist>.data/platlib/` is stripped, so the
#   .so ends up at <site-packages>/dakota/environment/environment.so .
#   delocate places its bundled libraries at the wheel's top-level `.dylibs/`,
#   which installs to <site-packages>/.dylibs/ — but it computes the
#   @loader_path-relative install names using the *wheel-internal* path of
#   the .so (4 levels deep), producing
#       @loader_path/../../../../.dylibs/lib*
#   That works for inspecting the wheel but is WRONG after install (it would
#   need to be @loader_path/../../.dylibs/lib*). We fix this up below by
#   rewriting the install names with install_name_tool.
#
# Limitation: delocate-wheel only inspects extension modules; the standalone
# `dakota` CLI binary in <dist>.data/scripts/ is not delocated. The Python
# `import dakota.environment` interface is fully self-contained and is what
# this wheel guarantees on macOS.
#
# Arguments (matching cibuildwheel's repair-wheel-command placeholders):
#   $1: destination directory for the repaired wheel
#   $2: source wheel
#   $3: target archs (e.g. "x86_64", "arm64", or "x86_64,arm64")

set -ex

DEST_DIR=$1
ORIG_WHEEL=$2
DELOCATE_ARCHS=${3:-$(uname -m)}

mkdir -p "${DEST_DIR}"

if ! command -v delocate-wheel >/dev/null 2>&1; then
    pip install --quiet delocate
fi

# Step 1: standard delocate-wheel pass to bundle dependencies.
# We exclude python interpreter shims because the wheel is installed into
# an existing Python and must not ship its own interpreter.
TMPDIR=$(mktemp -d)
delocate-wheel \
    --require-archs "${DELOCATE_ARCHS}" \
    --exclude libpython \
    --exclude Python.framework \
    -w "${TMPDIR}" \
    -v \
    "${ORIG_WHEEL}"

DELOCATED_WHEEL=$(ls "${TMPDIR}"/*.whl | head -1)
WHEEL_NAME=$(basename "${DELOCATED_WHEEL}" .whl)
WORKDIR="${TMPDIR}/work"
mkdir -p "${WORKDIR}"
unzip -q "${DELOCATED_WHEEL}" -d "${WORKDIR}"

# Step 2: drop the bundled `Python` shim if delocate copied it (it can be
# named just "Python" — the macOS framework binary). Excludes above usually
# catch this, but be defensive.
rm -f "${WORKDIR}/.dylibs/Python"

# NOTE on the standalone `dakota` CLI binary:
# py-build-cmake places the CLI at <dist>.data/scripts/dakota which installs
# to <venv>/bin/dakota. On macOS this binary links against the Python
# framework via a bare `Python` install_name (delocate rewrites it to point
# inside .dylibs/, but we exclude Python from bundling — a wheel must not
# ship its own interpreter). Making the CLI find the user's Python at
# runtime requires per-environment library path detection (framework vs
# pyenv vs conda) that is out of scope for the wheel-repair step. The CLI
# is therefore expected to fail at runtime on most macOS setups; the
# `import dakota.environment` Python interface is the supported usage.

# Step 3: rewrite install names to account for the .data/platlib indirection
# (see header comment). Replace any occurrence of
#   @loader_path/../../../../.dylibs/
# with
#   @loader_path/../../.dylibs/
# in every Mach-O file under the package directory that .data/platlib will
# install to <site-packages>/.
fix_install_names() {
    local f="$1"
    # otool -L lists each linked install name; rewrite anything pointing to
    # ../../../../.dylibs/ via @loader_path.
    otool -L "${f}" 2>/dev/null | awk 'NR>1 {print $1}' | while read -r oldname; do
        case "${oldname}" in
            @loader_path/../../../../.dylibs/*)
                newname="@loader_path/../../.dylibs/${oldname##*/.dylibs/}"
                install_name_tool -change "${oldname}" "${newname}" "${f}"
                ;;
        esac
    done
}

# Apply fix to all Mach-O files inside the wheel's .data/platlib tree
# (extension modules, dylibs, and the relocated dakota binary).
PLATLIB_ROOT=$(find "${WORKDIR}" -type d -path "*.data/platlib" | head -1)
if [ -n "${PLATLIB_ROOT}" ]; then
    while IFS= read -r f; do
        # Mach-O check via `file` magic — skip pure-python files.
        if file "${f}" | grep -q 'Mach-O'; then
            fix_install_names "${f}"
        fi
    done < <(find "${PLATLIB_ROOT}" -type f)
fi

# Step 4: re-codesign every Mach-O file we modified. macOS requires an
# ad-hoc signature (or stricter) for arm64 binaries to be loadable.
while IFS= read -r f; do
    if file "${f}" | grep -q 'Mach-O'; then
        codesign --force --sign - "${f}" 2>/dev/null || true
    fi
done < <(find "${WORKDIR}" -type f)

# Step 5: re-zip the wheel.
# We must update the RECORD file because we changed file contents.
# Easiest: use `wheel pack`.
if ! python3 -c "import wheel" 2>/dev/null; then
    pip install --quiet wheel
fi
python3 -m wheel pack --dest-dir "${DEST_DIR}" "${WORKDIR}"

rm -rf "${TMPDIR}"
