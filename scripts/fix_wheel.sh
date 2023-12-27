#!/bin/bash

set -ex

WHEEL_DIR=$1

WHEEL_NAME=$(basename $(ls ${WHEEL_DIR}/*.whl) .whl)

echo "Fixing ${WHEEL_DIR}/${WHEEL_NAME}.whl"

cd ${WHEEL_DIR}

unzip ${WHEEL_DIR}/${WHEEL_NAME}.whl -d ${WHEEL_NAME}

find ${WHEEL_NAME} -type f -name "*.so" -exec patchelf --set-rpath '$ORIGIN/../../itis_dakota.libs' '{}' \;
find ${WHEEL_NAME}/itis_dakota.libs -type f -name "*.so.*" -exec patchelf --set-rpath '$ORIGIN/' '{}' \;

cd ${WHEEL_NAME}
zip -r ${WHEEL_NAME}.whl *
mv ${WHEEL_NAME}.whl ..
