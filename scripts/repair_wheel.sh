#!/bin/bash
# Custom wheel repair script that works around a patchelf/auditwheel bug
# where the .dynamic/.dynstr sections end up outside LOAD segments for
# large ELF executables, causing SIGSEGV at runtime.
#
# The bug occurs because auditwheel's patchelf rewrites NEEDED entries
# and RPATH, which can shift sections across page boundaries. For some
# binary sizes (depending on the statically linked Python version), the
# .dynamic section ends up straddling a RW/R page boundary.
#
# Workaround: save the original dakota binary before auditwheel processes
# it, then after auditwheel finishes, restore the original and manually
# apply the NEEDED renames and RPATH using patchelf on the uncorrupted binary.

set -ex

PROJECT_ROOT="$(pwd)"
DEST_DIR=$1
ORIG_WHEEL=$2

# Point LD_LIBRARY_PATH at extracted TPL .so files for auditwheel scan.
LIBSCRATCH=$(mktemp -d)
unzip -o "${ORIG_WHEEL}" "*.data/scripts/*.so*" -d "${LIBSCRATCH}" || true
TPL_LIB_DIR=$(find "${LIBSCRATCH}" -type d -path "*.data/scripts" | head -1)
if [ -n "${TPL_LIB_DIR}" ]; then
    export LD_LIBRARY_PATH="${TPL_LIB_DIR}${LD_LIBRARY_PATH:+:${LD_LIBRARY_PATH}}"
fi

# Step 1: Save original dakota binary from pre-repair wheel
# In the pre-repair wheel, the binary is at itis_dakota-VERSION.data/scripts/dakota
# After auditwheel, it gets moved to itis_dakota.scripts/dakota
TMPDIR=$(mktemp -d)
unzip -o "${ORIG_WHEEL}" "*.data/scripts/dakota" -d "${TMPDIR}" || true
ORIG_BINARY=$(find "${TMPDIR}" -path "*.data/scripts/dakota" -type f | head -1)

if [ -z "${ORIG_BINARY}" ]; then
    echo "No dakota binary found in wheel, running standard repair"
    auditwheel repair -w "${DEST_DIR}" "${ORIG_WHEEL}"
    REPAIRED_WHEEL=$(ls "${DEST_DIR}"/*.whl | head -n1)
    python3 "${PROJECT_ROOT}/scripts/augment_sbom.py" --wheel "${REPAIRED_WHEEL}" --repo-root "${PROJECT_ROOT}"
    rm -rf "${TMPDIR}" "${LIBSCRATCH}"
    exit 0
fi

echo "Saved original dakota binary: ${ORIG_BINARY}"

# Step 2: Run auditwheel repair (this will corrupt the dakota binary)
auditwheel repair -w "${DEST_DIR}" "${ORIG_WHEEL}"

# Step 3: Unpack the repaired wheel
WHEEL_NAME=$(basename $(ls ${DEST_DIR}/*.whl) .whl)
echo "Fixing ${DEST_DIR}/${WHEEL_NAME}.whl"
cd "${DEST_DIR}"
unzip "${WHEEL_NAME}.whl" -d "${WHEEL_NAME}"

# Step 4: Build NEEDED name mapping from the libs directory
# auditwheel renames libs like libhdf5.so.103 -> libhdf5-HASH.so.103
# We need to figure out the mapping and apply it to the original binary
LIBS_DIR="${WHEEL_NAME}/itis_dakota.libs"
if [ -d "${LIBS_DIR}" ]; then
    # Get original NEEDED entries from the saved binary
    ORIG_NEEDED=$(patchelf --print-needed "${ORIG_BINARY}")

    # For each NEEDED entry, find matching hashed lib and rename
    # NEEDED has SONAME like "libhdf5_hl.so.100" but hashed file is
    # "libhdf5_hl-0b60eabd.so.100.1.2" - match on base name prefix.
    # Unversioned libs (libdakota_src.so) need handling too, not just N.M ones.
    for needed in ${ORIG_NEEDED}; do
        # Extract base name: everything before .so (and any version suffix)
        base=$(echo "${needed}" | sed -E 's/\.so(\..*)?$//')
        # Find hashed lib matching this base, e.g. libhdf5_hl-*.so*
        hashed_file=$(ls "${LIBS_DIR}/${base}"-*.so* 2>/dev/null | head -1)
        if [ -n "${hashed_file}" ]; then
            hashed_name=$(basename "${hashed_file}")
            echo "Renaming NEEDED: ${needed} -> ${hashed_name}"
            patchelf --replace-needed "${needed}" "${hashed_name}" "${ORIG_BINARY}"
        fi
    done

    # Set RPATH on the original binary
    patchelf --set-rpath '$ORIGIN/../itis_dakota.libs' "${ORIG_BINARY}"
fi

# Step 5: Replace the corrupted binary with the fixed original
# Only replace itis_dakota.scripts/dakota (the real binary), not .data/scripts/dakota (the wrapper)
CORRUPTED_BINARY=$(find "${WHEEL_NAME}" -path "*/itis_dakota.scripts/dakota" -type f | head -1)
if [ -n "${CORRUPTED_BINARY}" ]; then
    echo "Replacing corrupted binary: ${CORRUPTED_BINARY}"
    cp "${ORIG_BINARY}" "${CORRUPTED_BINARY}"
    chmod 755 "${CORRUPTED_BINARY}"
fi

# itis_dakota.scripts/*.so are dead-weight dupes of itis_dakota.libs/.
find "${WHEEL_NAME}/itis_dakota.scripts" -type f -name "*.so*" -print -delete
# .data/scripts/*.so only fed the LD_LIBRARY_PATH scan; drop them too.
find "${WHEEL_NAME}" -path "*.data/scripts/*.so*" -type f -print -delete
DIST_INFO_DIR=$(find "${WHEEL_NAME}" -maxdepth 1 -name "*.dist-info" | head -1)
if [ -n "${DIST_INFO_DIR}" ] && [ -f "${DIST_INFO_DIR}/RECORD" ]; then
    grep -v -E "^itis_dakota\.scripts/.*\.so|\.data/scripts/.*\.so" "${DIST_INFO_DIR}/RECORD" > "${DIST_INFO_DIR}/RECORD.tmp"
    mv "${DIST_INFO_DIR}/RECORD.tmp" "${DIST_INFO_DIR}/RECORD"
fi

# libboost_regex links ICU (~51MB) but uses zero symbols from it.
BOOST_REGEX_FILE=$(find "${WHEEL_NAME}/itis_dakota.libs" -maxdepth 1 -name "libboost_regex*.so*" -type f | head -1)
if [ -n "${BOOST_REGEX_FILE}" ]; then
    for icu_needed in $(patchelf --print-needed "${BOOST_REGEX_FILE}" | grep -i '^libicu'); do
        echo "Removing unused NEEDED: ${icu_needed}"
        patchelf --remove-needed "${icu_needed}" "${BOOST_REGEX_FILE}"
    done
    find "${WHEEL_NAME}/itis_dakota.libs" -maxdepth 1 -name "libicu*.so*" -type f -print -delete
    if [ -n "${DIST_INFO_DIR}" ] && [ -f "${DIST_INFO_DIR}/RECORD" ]; then
        grep -v -E "itis_dakota\.libs/libicu(data|i18n|uc)-.*\.so" "${DIST_INFO_DIR}/RECORD" > "${DIST_INFO_DIR}/RECORD.tmp"
        mv "${DIST_INFO_DIR}/RECORD.tmp" "${DIST_INFO_DIR}/RECORD"
    fi
fi

# Step 6: fix RPATH depth (rel. to platlib root); skip wrapper stubs.
find "${WHEEL_NAME}" -type f -name "*.so" | while read -r so_file; do
    if ! head -c4 "${so_file}" | cmp -s - <(printf '\177ELF'); then
        echo "Skipping non-ELF file: ${so_file}"
        continue
    fi
    so_dir=$(dirname "${so_file}")
    root_dir="${WHEEL_NAME}"
    platlib_root=$(echo "${so_dir}" | grep -o '.*\.data/platlib' || true)
    if [ -n "${platlib_root}" ]; then
        root_dir="${platlib_root}"
    fi
    rel_to_root=$(realpath --relative-to="${so_dir}" "${root_dir}")
    patchelf --set-rpath "\$ORIGIN/${rel_to_root}/itis_dakota.libs" "${so_file}"
done
find "${WHEEL_NAME}/itis_dakota.libs" -type f -name "*.so.*" -exec patchelf --set-rpath '$ORIGIN/' '{}' \;

# Strip local/debug symbols (-7.5% wheel size); keep dynsym for dlopen.
find "${WHEEL_NAME}" -type f \( -name "*.so*" -o -path "*itis_dakota.scripts/dakota" \) | while read -r elf_file; do
    if head -c4 "${elf_file}" | cmp -s - <(printf '\177ELF'); then
        strip --strip-unneeded "${elf_file}"
    fi
done

# Step 7: Re-zip the wheel
cd "${WHEEL_NAME}"
zip -r "${WHEEL_NAME}.whl" *
mv "${WHEEL_NAME}.whl" ..
cd "${DEST_DIR}"

# Step 8: Verify the wheel is a valid zip
python3 - <<PYEOF
import zipfile, sys
whl = "${WHEEL_NAME}.whl"
with zipfile.ZipFile(whl) as zf:
    bad = zf.testzip()
    if bad:
        print(f"ERROR: testzip() reports bad entry: {bad}", file=sys.stderr)
        sys.exit(1)
    print(f"Wheel zip verification passed for {whl}")
PYEOF

# Step 9: Augment the embedded SBOM with numpy + vendored source components
python3 "${PROJECT_ROOT}/scripts/augment_sbom.py" --wheel "${WHEEL_NAME}.whl" --repo-root "${PROJECT_ROOT}"

# Step 10: work around Docker Desktop docker-cp page-cache corruption by also writing through the project bind mount
python3 -c "import os; fd=os.open('${WHEEL_NAME}.whl', os.O_RDONLY); os.fsync(fd); os.close(fd)"
sync
SAFE_DIR=/project/.cibw_wheels_safe
if mkdir -p "${SAFE_DIR}" 2>/dev/null && [ -w "${SAFE_DIR}" ]; then
    cp -f "${WHEEL_NAME}.whl" "${SAFE_DIR}/${WHEEL_NAME}.whl"
    sync
    echo "Wrote safe copy to ${SAFE_DIR}/${WHEEL_NAME}.whl"
else
    echo "WARNING: ${SAFE_DIR} not writable, no safe copy written" >&2
fi

# Cleanup
rm -rf "${TMPDIR}" "${LIBSCRATCH}"
