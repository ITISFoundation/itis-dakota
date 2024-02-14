cmake_minimum_required(VERSION 3.15)
project(itis_dakota)

add_definitions(-w)

find_package(Threads REQUIRED)

set(PY_BUILD_CMAKE_BIN_DIRECTORY ${PY_BUILD_CMAKE_PACKAGE_NAME}-${PY_BUILD_CMAKE_PACKAGE_VERSION}.data/scripts)
set(PY_BUILD_CMAKE_LIB_DIRECTORY ${PY_BUILD_CMAKE_PACKAGE_NAME}-${PY_BUILD_CMAKE_PACKAGE_VERSION}.data/platlib)

add_subdirectory(dakota EXCLUDE_FROM_ALL)

add_custom_target(dakota_for_python ALL DEPENDS environment dakota_src ${Dakota_TPL_LIBRARIES})

#install(TARGETS dakota
#        RUNTIME
#        COMPONENT dakota_for_python
#        DESTINATION ${PY_BUILD_CMAKE_BIN_DIRECTORY})

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
