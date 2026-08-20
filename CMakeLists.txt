cmake_minimum_required(VERSION 3.15)
project(itis_dakota)


find_package(Threads REQUIRED)

set(PY_BUILD_CMAKE_BIN_DIRECTORY ${PY_BUILD_CMAKE_PACKAGE_NAME}-${PY_BUILD_CMAKE_PACKAGE_VERSION}.data/scripts)
set(PY_BUILD_CMAKE_LIB_DIRECTORY ${PY_BUILD_CMAKE_PACKAGE_NAME}-${PY_BUILD_CMAKE_PACKAGE_VERSION}.data/platlib)

add_compile_options(-w)
# add_compile_options(-Wno-psabi)
add_compile_definitions(BOOST_BIND_GLOBAL_PLACEHOLDERS)

# Enables -dead_strip/--gc-sections below to drop unused template code.
add_compile_options(-ffunction-sections -fdata-sections)
if(APPLE)
    # Apple's ld equivalent of GNU --gc-sections.
    set(CMAKE_EXE_LINKER_FLAGS "${CMAKE_EXE_LINKER_FLAGS} -Wl,-dead_strip")
    set(CMAKE_SHARED_LINKER_FLAGS "${CMAKE_SHARED_LINKER_FLAGS} -Wl,-dead_strip")
else()
    set(CMAKE_EXE_LINKER_FLAGS "${CMAKE_EXE_LINKER_FLAGS} -Wl,--gc-sections")
    set(CMAKE_SHARED_LINKER_FLAGS "${CMAKE_SHARED_LINKER_FLAGS} -Wl,--gc-sections")
endif()

set(DAKOTA_SCHEMA_PATH ${CMAKE_CURRENT_SOURCE_DIR}/dakota/src/dakota.json CACHE STRING "Dakota Schema file")
set(DAKOTA_XML_INPUT ${CMAKE_CURRENT_SOURCE_DIR}/dakota/src/dakota.xml CACHE STRING "Dakota XML grammar file")

add_subdirectory(dakota EXCLUDE_FROM_ALL)

# Freeze __DATE__, __TIME__, and QUESO_BUILD_DATE to constant strings so
# ccache can cache QUESO object files across rebuilds (~150 files).
# Without this, every QUESO .C file expands __DATE__/__TIME__ via assert
# macros in asserts.h / Defines.h, producing unique preprocessed output
# on every build and defeating ccache's hashing.
target_compile_options(queso PRIVATE -Wno-builtin-macro-redefined)
target_compile_definitions(queso PRIVATE
  __DATE__="Dakota 6.24"
  __TIME__="00:00:00"
  QUESO_BUILD_DATE="Dakota 6.24"
)

# Same for dakota_src: DakotaBuildInfo.hpp uses __DATE__/__TIME__ inline,
# affecting ~9 files (OutputManager, RestartVersion, dakota_python, etc.)
target_compile_options(dakota_src PRIVATE -Wno-builtin-macro-redefined)
target_compile_definitions(dakota_src PRIVATE
  __DATE__="Dakota 6.24"
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

# Glob+install whatever TPL .so/.dylib got built, for auditwheel/delocate.
install(CODE "
  file(GLOB_RECURSE _dakota_tpl_shared_libs
       \"${CMAKE_CURRENT_BINARY_DIR}/dakota/*.so\"
       \"${CMAKE_CURRENT_BINARY_DIR}/dakota/*.so.*\"
       \"${CMAKE_CURRENT_BINARY_DIR}/dakota/*.dylib\")
  list(FILTER _dakota_tpl_shared_libs EXCLUDE REGEX \"/libdakota_src\\\\.(so|dylib)|/environment\\\\.\")
  foreach(_lib IN LISTS _dakota_tpl_shared_libs)
    file(INSTALL DESTINATION \"\${CMAKE_INSTALL_PREFIX}/${PY_BUILD_CMAKE_BIN_DIRECTORY}\"
         TYPE SHARED_LIBRARY
         FOLLOW_SYMLINK_CHAIN
         FILES \"\${_lib}\")
  endforeach()
"
COMPONENT dakota_for_python)

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

if(APPLE)
    # Add @loader_path (delocate needs it); skip if gfortran already added it.
    install(CODE "
      function(add_rpath_if_missing _f _rpath)
        execute_process(COMMAND otool -l \"\${_f}\" OUTPUT_VARIABLE _existing_rpaths)
        string(FIND \"\${_existing_rpaths}\" \"path \${_rpath} (offset\" _rpath_idx)
        if(_rpath_idx EQUAL -1)
          execute_process(COMMAND install_name_tool -add_rpath \"\${_rpath}\" \"\${_f}\")
        endif()
      endfunction()
      file(GLOB _dakota_bin_dir_dylibs
           \"\${CMAKE_INSTALL_PREFIX}/${PY_BUILD_CMAKE_BIN_DIRECTORY}/*.dylib\")
      foreach(_f IN LISTS _dakota_bin_dir_dylibs)
        add_rpath_if_missing(\"\${_f}\" \"@loader_path\")
      endforeach()
      add_rpath_if_missing(\"\${CMAKE_INSTALL_PREFIX}/${PY_BUILD_CMAKE_BIN_DIRECTORY}/dakota\" \"@loader_path\")
      file(GLOB _dakota_environment_module
           \"\${CMAKE_INSTALL_PREFIX}/${PY_BUILD_CMAKE_LIB_DIRECTORY}/dakota/environment/environment*.so\")
      foreach(_f IN LISTS _dakota_environment_module)
        add_rpath_if_missing(\"\${_f}\" \"@loader_path/../../../scripts\")
      endforeach()
    "
    COMPONENT dakota_for_python)
endif()
