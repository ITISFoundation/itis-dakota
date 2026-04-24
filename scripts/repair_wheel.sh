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

DEST_DIR=$1
ORIG_WHEEL=$2

# Step 1: Save original dakota binary from pre-repair wheel
# In the pre-repair wheel, the binary is at itis_dakota-VERSION.data/scripts/dakota
# After auditwheel, it gets moved to itis_dakota.scripts/dakota
TMPDIR=$(mktemp -d)
unzip -o "${ORIG_WHEEL}" "*.data/scripts/dakota" -d "${TMPDIR}" || true
ORIG_BINARY=$(find "${TMPDIR}" -path "*.data/scripts/dakota" -type f | head -1)

if [ -z "${ORIG_BINARY}" ]; then
    echo "No dakota binary found in wheel, running standard repair"
    auditwheel repair -w "${DEST_DIR}" "${ORIG_WHEEL}"
    rm -rf "${TMPDIR}"
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
    # "libhdf5_hl-0b60eabd.so.100.1.2" - match on base name prefix
    for needed in ${ORIG_NEEDED}; do
        # Extract base name: everything before .so
        base=$(echo "${needed}" | sed 's/\.so\..*//')
        # Find hashed lib matching this base (e.g. libhdf5_hl-*.so.*)
        hashed_file=$(ls "${LIBS_DIR}/${base}"-*.so.* 2>/dev/null | head -1)
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

# Step 6: Fix RPATH on .so files (same as original fix_wheel.sh)
find "${WHEEL_NAME}" -type f -name "*.so" -exec patchelf --set-rpath '$ORIGIN/../../itis_dakota.libs' '{}' \;
find "${WHEEL_NAME}/itis_dakota.libs" -type f -name "*.so.*" -exec patchelf --set-rpath '$ORIGIN/' '{}' \;

# Step 7: Re-zip the wheel
cd "${WHEEL_NAME}"
zip -r "${WHEEL_NAME}.whl" *
mv "${WHEEL_NAME}.whl" ..

# Cleanup
rm -rf "${TMPDIR}"
