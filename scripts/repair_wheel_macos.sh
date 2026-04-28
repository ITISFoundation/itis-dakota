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

set -euo pipefail

DEST_DIR=$1
ORIG_WHEEL=$2
DELOCATE_ARCHS=${3:-$(uname -m)}

mkdir -p "${DEST_DIR}"

if ! command -v delocate-wheel >/dev/null 2>&1; then
    python3 -m pip install --quiet delocate
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

# Step 2b: relocate the standalone `dakota` CLI binary.
#
# py-build-cmake puts the binary at <dist>.data/scripts/dakota which installs
# to <venv>/bin/dakota. From that location the relative path to
# <site-packages>/.dylibs/ varies by Python version and is not predictable.
# The binary also needs libpython at runtime (Dakota embeds a Python
# interpreter for its PYTHON_DIRECT_INTERFACE).
#
# Solution: move the real binary into
#   <dist>.data/platlib/itis_dakota/.bin/dakota
# (which installs to <site-packages>/itis_dakota/.bin/dakota — a fixed
# relative location to <site-packages>/.dylibs/). Then replace the script
# entry point with a tiny Python wrapper that:
#   1) Locates the real binary via the itis_dakota package
#   2) Discovers libpython via sysconfig and injects it into
#      DYLD_LIBRARY_PATH so the binary can find the interpreter at runtime
#   3) exec's the real binary

SCRIPT_DAKOTA=$(find "${WORKDIR}" -type f -path "*.data/scripts/dakota" | head -1)
if [ -n "${SCRIPT_DAKOTA}" ]; then
    PLATLIB_DIR=$(find "${WORKDIR}" -type d -path "*.data/platlib" | head -1)
    if [ -z "${PLATLIB_DIR}" ]; then
        echo "ERROR: cannot locate .data/platlib in wheel" >&2
        exit 1
    fi
    BIN_DEST_DIR="${PLATLIB_DIR}/itis_dakota/.bin"
    mkdir -p "${BIN_DEST_DIR}"
    mv "${SCRIPT_DAKOTA}" "${BIN_DEST_DIR}/dakota"
    chmod 755 "${BIN_DEST_DIR}/dakota"

    # Rewrite the relocated binary's @loader_path references:
    # It was previously at .data/scripts/ (2 levels deep from wheel root),
    # so delocate wrote @loader_path/../../.dylibs/. Now it lives at
    # .data/platlib/itis_dakota/.bin/ (4 levels deep from wheel root), but
    # after install it will be at itis_dakota/.bin/ (2 levels from
    # site-packages root, where .dylibs/ lives). So @loader_path/../../.dylibs/
    # is the correct installed path — no change needed! Leave the binary's
    # install names as-is.

    # Write the Python wrapper script.
    cat > "${SCRIPT_DAKOTA}" <<'PYEOF'
#!/usr/bin/env python3
"""Wrapper that exec's the bundled dakota binary inside itis_dakota.

Created by scripts/repair_wheel_macos.sh during wheel repair.
On macOS the dakota binary dynamically links against "Python" (the macOS
framework name). This wrapper:
  1) Locates the real binary bundled inside the itis_dakota package.
  2) Discovers the host Python's shared library via sysconfig.
  3) Creates a directory containing a "Python" symlink that points to the
     real libpython (works for pyenv, Homebrew, python.org framework, etc.).
  4) Injects that directory plus .dylibs/ into DYLD_LIBRARY_PATH.
  5) exec's the real binary.
"""
import os
import sys
import sysconfig
import tempfile


def _find_python_lib():
    """Return path to the Python shared library / framework binary."""
    libdir = sysconfig.get_config_var("LIBDIR") or ""
    ldlib = sysconfig.get_config_var("LDLIBRARY") or ""
    # Framework builds put the binary at e.g.
    # .../Python.framework/Versions/3.12/Python
    # IMPORTANT: use the versioned path (Versions/X.Y/Python), NOT the
    # unversioned /Python.framework/Python symlink, which resolves to
    # Versions/Current and may point to a different Python version.
    fwprefix = sysconfig.get_config_var("PYTHONFRAMEWORKPREFIX") or ""
    fwdir = sysconfig.get_config_var("PYTHONFRAMEWORKDIR") or ""
    if fwprefix and fwdir and fwdir != "no-framework":
        ver = "%d.%d" % (sys.version_info.major, sys.version_info.minor)
        candidate = os.path.join(fwprefix, fwdir, "Versions", ver, "Python")
        if os.path.isfile(candidate):
            return candidate
        # Fallback to unversioned path (single-version installs)
        candidate = os.path.join(fwprefix, fwdir, "Python")
        if os.path.isfile(candidate):
            return candidate
    # Non-framework (pyenv, Homebrew, etc.): libpython3.X.dylib
    candidate = os.path.join(libdir, ldlib)
    if os.path.isfile(candidate):
        return candidate
    return None


def _main():
    import itis_dakota
    pkg_dir = os.path.dirname(os.path.abspath(itis_dakota.__file__))
    binary = os.path.join(pkg_dir, ".bin", "dakota")
    if not os.path.isfile(binary):
        sys.stderr.write(
            "itis_dakota: bundled dakota binary not found at %s\n" % binary
        )
        sys.exit(1)

    # .dylibs/ lives at <site-packages>/.dylibs/
    dylibs_dir = os.path.normpath(os.path.join(pkg_dir, "..", ".dylibs"))

    # The binary links against the bare name "Python". Create a temp
    # directory with a "Python" symlink pointing at the real library so
    # DYLD_LIBRARY_PATH can resolve it.
    python_lib = _find_python_lib()
    extra_paths = []
    if os.path.isdir(dylibs_dir):
        extra_paths.append(dylibs_dir)

    tmpdir = None
    if python_lib:
        tmpdir = tempfile.mkdtemp(prefix="itis_dakota_")
        link_path = os.path.join(tmpdir, "Python")
        os.symlink(python_lib, link_path)
        extra_paths.insert(0, tmpdir)

    current = os.environ.get("DYLD_LIBRARY_PATH", "")
    if extra_paths:
        new_val = ":".join(extra_paths)
        if current:
            new_val = new_val + ":" + current
        os.environ["DYLD_LIBRARY_PATH"] = new_val

    # exec replaces this process; the tmpdir will be cleaned up by the OS
    # when the process exits (it only contains a single symlink).
    os.execv(binary, [binary] + sys.argv[1:])


if __name__ == "__main__":
    _main()
PYEOF
    chmod 755 "${SCRIPT_DAKOTA}"
fi

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
    while read -r oldname; do
        case "${oldname}" in
            @loader_path/../../../../.dylibs/*)
                newname="@loader_path/../../.dylibs/${oldname##*/.dylibs/}"
                install_name_tool -change "${oldname}" "${newname}" "${f}"
                ;;
            @loader_path/../../../../itis_dakota/.dylibs/*)
                newname="@loader_path/../../itis_dakota/.dylibs/${oldname##*/.dylibs/}"
                install_name_tool -change "${oldname}" "${newname}" "${f}"
                ;;
        esac
    done < <(otool -L "${f}" 2>/dev/null | awk 'NR>1 {print $1}')
}

# Apply fix to all Mach-O files inside the wheel's .data/platlib tree
# (extension modules, dylibs, and the relocated dakota binary).
PLATLIB_ROOT=$(find "${WORKDIR}" -type d -path "*.data/platlib" | head -1)
if [ -n "${PLATLIB_ROOT}" ]; then
    while IFS= read -r f; do
        if file "${f}" | grep -q 'Mach-O'; then
            fix_install_names "${f}"
        fi
    done < <(find "${PLATLIB_ROOT}" -type f)
fi

# Also rewrite the Python install_name in the relocated dakota binary so it
# uses @rpath instead of a hardcoded path. The wrapper script sets
# DYLD_LIBRARY_PATH, but @rpath provides an additional fallback.
RELOCATED_DAKOTA=$(find "${WORKDIR}" -type f -path "*/itis_dakota/.bin/dakota" | head -1)
if [ -n "${RELOCATED_DAKOTA}" ]; then
    # Rewrite any @loader_path/.../.dylibs/Python reference to just "Python"
    # (bare name — resolved at runtime via DYLD_LIBRARY_PATH set by wrapper).
    while read -r oldname; do
        case "${oldname}" in
            */.dylibs/Python|*/Python.framework/*)
                install_name_tool -change "${oldname}" "Python" "${RELOCATED_DAKOTA}"
                ;;
        esac
    done < <(otool -L "${RELOCATED_DAKOTA}" 2>/dev/null | awk 'NR>1 {print $1}')
fi

# Step 4: re-codesign every Mach-O file we modified. macOS requires an
# ad-hoc signature (or stricter) for arm64 binaries to be loadable.
while IFS= read -r f; do
    if file "${f}" | grep -q 'Mach-O'; then
        codesign --force --sign - "${f}"
    fi
done < <(find "${WORKDIR}" -type f)

# Step 5: re-zip the wheel.
# We must update the RECORD file because we changed file contents.
# Easiest: use `wheel pack`.
if ! python3 -c "import wheel" 2>/dev/null; then
    python3 -m pip install --quiet wheel
fi
python3 -m wheel pack --dest-dir "${DEST_DIR}" "${WORKDIR}"

rm -rf "${TMPDIR}"
