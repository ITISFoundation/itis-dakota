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
    if(WIN32)
        # binutils only auto-exports every symbol when the link carries no
        # __declspec(dllexport) anywhere; vendored headers decorate for _WIN32
        # (ampl funcadd.h, approxnn ANN.h), which silently reduces each DLL's
        # import library to a handful of decorated symbols and starves the
        # closed-world links of every sibling DLL. Force full export.
        set(CMAKE_SHARED_LINKER_FLAGS "${CMAKE_SHARED_LINKER_FLAGS} -Wl,--export-all-symbols")
        # Side effect of the above: a DLL that statically absorbed an archive
        # (colin.dll + libamplsolver.a, B5fe) copy-exports those members into
        # its import library; a consumer linking BOTH (libdakota_src wants
        # ASL_alloc directly and colin for Colin::) hits multiple-definition
        # between the archive member and colin's copy. The copy wins with
        # --allow-multiple-definition (it precedes on the line): every ASL
        # user shares colin.dll's single core, exactly the shared-core layout
        # from amplsolver's own-DLL era. Exe/module links carry the flag as
        # the same interface expansion reaches them.
        foreach(_dk_lk CMAKE_SHARED_LINKER_FLAGS CMAKE_EXE_LINKER_FLAGS CMAKE_MODULE_LINKER_FLAGS)
            set(${_dk_lk} "${${_dk_lk}} -Wl,--allow-multiple-definition")
        endforeach()
    else()
        # mingw: --gc-sections at DLL link time strips auto-exported sections
        # whose only callers live in other DLLs (observed on msys2 binutils),
        # breaking closed-world DLL links. Exe links keep gc-sections; only
        # the Windows wheel loses the size optimization.
        set(CMAKE_SHARED_LINKER_FLAGS "${CMAKE_SHARED_LINKER_FLAGS} -Wl,--gc-sections")
    endif()
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

# mingw shared-library links are closed-world; these targets referenced
# libraries they never linked, relying on ELF runtime resolution.  Spell out
# the edges (harmless no-ops on Linux/macOS): queso calls GSL; hopspack and
# surfpack_fortran call BLAS/LAPACK routines (dgemm_, dswap_, xerbla_, ...).
# dakota only caches these finds inside subdirectory scopes (TPL_* vars are
# trilinos-local; imported targets are not parent-visible), so re-run the
# find-modules here: they reuse dakota's cache hits and expose the documented
# *_LIBRARIES cache variables at root scope.
find_package(GSL QUIET)
find_package(BLAS QUIET)
find_package(LAPACK QUIET)
# Use the plain signature: queso/hopspack/surfpack_fortran already use it in
# dakota's tree and CMake forbids mixing signatures per target.
if(TARGET queso AND GSL_LIBRARIES)
  target_link_libraries(queso ${GSL_LIBRARIES})
endif()
if(TARGET hopspack AND BLAS_LIBRARIES)
  target_link_libraries(hopspack ${LAPACK_LIBRARIES} ${BLAS_LIBRARIES})
endif()
if(TARGET surfpack_fortran AND BLAS_LIBRARIES)
  target_link_libraries(surfpack_fortran ${LAPACK_LIBRARIES} ${BLAS_LIBRARIES})
endif()
# surfpack calls into pecos (CrossValidationIterator, CompressedSensingTool;
# the edge was commented out upstream at src/CMakeLists.txt:82 and ELF
# resolved it at runtime). pecos never references surfpack, so this stays a
# forward edge. Plain signature to match dakota's uses.
if(TARGET surfpack AND TARGET pecos_src)
  target_link_libraries(surfpack pecos_src)
endif()
if(TARGET surfpack AND TARGET conmin)
  target_link_libraries(surfpack conmin)
endif()
# NKM_Optimize.cpp also calls the NCSUOpt direct solver (ncsuopt_direct_);
# same ELF-load-time-resolution class as conmin. NCSUOpt is a leaf.
if(TARGET surfpack AND TARGET ncsuopt)
  target_link_libraries(surfpack ncsuopt)
endif()
# mingw: DLL links are closed-world. On ELF, dakota_src.so deliberately
# leaves its TPL symbols undefined and lets the executables/extension
# module resolve them at load time (the dakota exe links the full stack).
# PE requires every DLL to close, so mirror the exe's library set onto
# dakota_src; TARGET-guarded names auto-skip whatever a config doesn't
# build. Two constraints shape the mechanism: dakota_src is plain-
# signature and install/export()'d, so any PUBLIC target dep not in the
# DakotaTargets export set breaks generation (even behind
# $<LINK_ONLY:>), and raw target names appended to the LINK_LIBRARIES
# property are still validated too. The form that passes is the raw
# property fed $<TARGET_LINKER_FILE:...> ITEMS: file paths, not target
# names, so neither the interface nor the export target graph ever sees
# them. Scoped to Windows (plus an option for the Linux closed-world
# emulation rig) so shipping Linux/macOS artifacts stay bit-identical.
option(DAKOTA_FORCE_CLOSED_WORLD_LINKS
       "Mirror mingw closed-world dakota_src links on ELF (verification)" OFF)
if(TARGET dakota_src AND (WIN32 OR DAKOTA_FORCE_CLOSED_WORLD_LINKS))
  foreach(_dk_tpl approxnn conmin cport ddace dfftpack dream eutils ethreads
                  fsudace hopspack jega jega_fe lhs lhs_mod lhs_mods moga
                  ncsuopt nidr nomad optpp pecos_src pecos_util psuade queso
                  soga sparsegrid surfpack surfpack_fortran utilib utilities)
    if(TARGET ${_dk_tpl})
      set_property(TARGET dakota_src APPEND PROPERTY LINK_LIBRARIES
                   "$<TARGET_LINKER_FILE:${_dk_tpl}>")
    endif()
  endforeach()
  # The JEGA family is STATIC under mingw (B-static family), and its
  # archives reference each other (moga/soga -> jega's MetricTracker*,
  # jega/moga/soga -> eddy::utilities RNG, jega_fe <-> jega). GNU ld
  # takes a single left-to-right pass per archive, so the alphabetical
  # order above starves late requesters. Second pass over the family
  # re-scans the archives once more, resolving every cross edge. Shared
  # DLL links are order-insensitive, so only the static family repeats.
  foreach(_dk_rescan jega jega_fe moga soga utilities eutils ethreads)
    if(TARGET ${_dk_rescan})
      set_property(TARGET dakota_src APPEND PROPERTY LINK_LIBRARIES
                   "$<TARGET_LINKER_FILE:${_dk_rescan}>")
    endif()
  endforeach()
  if(GSL_LIBRARIES)
    set_property(TARGET dakota_src APPEND PROPERTY LINK_LIBRARIES ${GSL_LIBRARIES})
  endif()
  # dakota finds HDF5 in its own scope; re-run (cache-warm) so the
  # component variables/targets exist here, preferring imported targets.
  find_package(HDF5 QUIET COMPONENTS "C;HL;CXX")
  foreach(_h5 hdf5::hdf5 hdf5::hdf5_cpp hdf5::hdf5_hl hdf5::hdf5_hl_cpp)
    if(TARGET ${_h5})
      set_property(TARGET dakota_src APPEND PROPERTY LINK_LIBRARIES
                   "$<TARGET_LINKER_FILE:${_h5}>")
    endif()
  endforeach()
  if(NOT TARGET hdf5::hdf5 AND HDF5_CXX_LIBRARIES)
    set_property(TARGET dakota_src APPEND PROPERTY LINK_LIBRARIES
                 ${HDF5_CXX_LIBRARIES} ${HDF5_C_LIBRARIES})
  endif()
  # dakota_src embeds the Python interpreter; on ELF the hosting
  # executable supplies the API at runtime, mingw wants the python3xx
  # import lib in every DLL that calls it. Re-find at root scope so the
  # imported target exists here (dakota found it inside its own scope);
  # TARGET_LINKER_FILE resolves to python3xx.lib on mingw.
  if(NOT TARGET Python3::Python)
    find_package(Python3 QUIET COMPONENTS Interpreter Development.Embed)
  endif()
  if(TARGET Python3::Python)
    set_property(TARGET dakota_src APPEND PROPERTY LINK_LIBRARIES
                 "$<TARGET_LINKER_FILE:Python3::Python>")
  endif()
endif()
# dakota.exe is closed-world under mingw too; its link omits ethreads
# on ELF (nothing demanded it), so carry the same file-form edge.
if(WIN32 AND TARGET dakota AND TARGET ethreads)
  set_property(TARGET dakota APPEND PROPERTY LINK_LIBRARIES
               "$<TARGET_LINKER_FILE:ethreads>")
endif()

add_custom_target(dakota_for_python ALL DEPENDS environment dakota_src dakota)

install(TARGETS dakota
        RUNTIME
        COMPONENT dakota_for_python
        DESTINATION ${PY_BUILD_CMAKE_BIN_DIRECTORY})

install(TARGETS dakota_src
        LIBRARY
        COMPONENT dakota_for_python
        LIBRARY DESTINATION ${PY_BUILD_CMAKE_BIN_DIRECTORY}
        # On Windows the SHARED runtime artifact is a DLL, installed under
        # the RUNTIME kind (LIBRARY applies only on unix). No RUNTIME
        # artifact exists on Linux/macOS, so this is a no-op there.
        RUNTIME DESTINATION ${PY_BUILD_CMAKE_BIN_DIRECTORY})

# Glob+install whatever TPL .so/.dylib/.dll got built, for auditwheel/delocate/
# delvewheel. On mingw a built SHARED TPL is lib<name>.dll (+ lib<name>.dll.a
# import lib, which the *.dll pattern skips).
install(CODE "
  file(GLOB_RECURSE _dakota_tpl_shared_libs
       \"${CMAKE_CURRENT_BINARY_DIR}/dakota/*.so\"
       \"${CMAKE_CURRENT_BINARY_DIR}/dakota/*.so.*\"
       \"${CMAKE_CURRENT_BINARY_DIR}/dakota/*.dylib\"
       \"${CMAKE_CURRENT_BINARY_DIR}/dakota/*.dll\")
  list(FILTER _dakota_tpl_shared_libs EXCLUDE REGEX \"/libdakota_src\\\\.(so|dylib|dll)|/environment\\\\.\")
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

install(FILES stubs/dakota/environment/__init__.pyi
              stubs/dakota/environment/environment.pyi
              stubs/dakota/environment/py.typed
    COMPONENT dakota_for_python
    DESTINATION ${PY_BUILD_CMAKE_LIB_DIRECTORY}/dakota/environment/)

# Dakota's own Pydantic models for its native JSON input format (the same
# models that generate dakota.json / drive the C++ JSON parser codegen).
# Pure Python, no compiled dependency, so it ships as plain source.
install(DIRECTORY dakota/python/dakota/spec
    COMPONENT dakota_for_python
    DESTINATION ${PY_BUILD_CMAKE_LIB_DIRECTORY}/dakota/
    PATTERN "__pycache__" EXCLUDE
    PATTERN "*.py[cdo]" EXCLUDE)

# dakota.spec ships inline types, so it needs its own empty PEP 561 marker:
# dakota/ is a namespace package, so environment/'s py.typed doesn't cover it.
file(WRITE ${CMAKE_CURRENT_BINARY_DIR}/spec_py.typed "")
install(FILES ${CMAKE_CURRENT_BINARY_DIR}/spec_py.typed
    COMPONENT dakota_for_python
    DESTINATION ${PY_BUILD_CMAKE_LIB_DIRECTORY}/dakota/spec/
    RENAME py.typed)

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
