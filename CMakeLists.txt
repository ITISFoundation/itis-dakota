cmake_minimum_required(VERSION 3.15)
project(itis_dakota)


find_package(Threads REQUIRED)

set(PY_BUILD_CMAKE_BIN_DIRECTORY ${PY_BUILD_CMAKE_PACKAGE_NAME}-${PY_BUILD_CMAKE_PACKAGE_VERSION}.data/scripts)
set(PY_BUILD_CMAKE_LIB_DIRECTORY ${PY_BUILD_CMAKE_PACKAGE_NAME}-${PY_BUILD_CMAKE_PACKAGE_VERSION}.data/platlib)

add_compile_options(-w)
# add_compile_options(-Wno-psabi)
add_compile_definitions(BOOST_BIND_GLOBAL_PLACEHOLDERS)
add_subdirectory(dakota EXCLUDE_FROM_ALL)

# Freeze __DATE__, __TIME__, and QUESO_BUILD_DATE to constant strings so
# sccache can cache QUESO object files across rebuilds (~150 files).
# Without this, every QUESO .C file expands __DATE__/__TIME__ via assert
# macros in asserts.h / Defines.h, producing unique preprocessed output
# on every build and defeating sccache's preprocessor-mode hashing.
target_compile_options(queso PRIVATE -Wno-builtin-macro-redefined)
target_compile_definitions(queso PRIVATE
  __DATE__="Dakota 6.23"
  __TIME__="00:00:00"
  QUESO_BUILD_DATE="Dakota 6.23"
)

# Same for dakota_src: DakotaBuildInfo.hpp uses __DATE__/__TIME__ inline,
# affecting ~9 files (OutputManager, RestartVersion, dakota_python, etc.)
target_compile_options(dakota_src PRIVATE -Wno-builtin-macro-redefined)
target_compile_definitions(dakota_src PRIVATE
  __DATE__="Dakota 6.23"
  __TIME__="00:00:00"
)

add_custom_target(dakota_for_python ALL DEPENDS environment dakota_src dakota)

install(TARGETS dakota
        RUNTIME
        COMPONENT dakota_for_python
        DESTINATION ${PY_BUILD_CMAKE_BIN_DIRECTORY})

install(TARGETS dakota_src
        LIBRARY
        COMPONENT dakota_for_python
        LIBRARY DESTINATION ${PY_BUILD_CMAKE_BIN_DIRECTORY})

#install(PROGRAMS ${Dakota_TPL_LIBRARIES} 
#   COMPONENT dakota_for_python
#    DESTINATION ${PY_BUILD_CMAKE_LIB_DIRECTORY}/dakota/environment/)

install(TARGETS environment
    LIBRARY
    COMPONENT dakota_for_python
    LIBRARY DESTINATION ${PY_BUILD_CMAKE_LIB_DIRECTORY}/dakota/environment/)

install(FILES dakota/src/__init__.py
    COMPONENT dakota_for_python
    DESTINATION ${PY_BUILD_CMAKE_LIB_DIRECTORY}/dakota/environment/)
