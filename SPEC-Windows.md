# SPEC-Windows — itis-dakota win_amd64 wheel (PoC)

## §G Goal

Produce `itis_dakota` `win_amd64` wheel from same Dakota 6.24.0 source + patches, via
cibuildwheel on `windows-*` GitHub runner with MSYS2/MinGW-w64 (ucrt64) toolchain.
PoC scope: cp313 only, CI artifact only, ⊥ PyPI publish.

## §C Constraints

- C.src — same source as linux/macos legs: `DAKOTA_SRC_TARBALL_URL` v6.24.0 tarball + all
  `src_patches_v624/*.patch` applied identically. New mingw fixes live as extra patches in
  same folder, portable across platforms (Windows-only behavior behind `__MINGW32__`/
  platform guards, ⊥ separate Windows source fork).
- C.toolchain — MSYS2 ucrt64 `gcc`/`g++`/`gfortran` build Dakota, QUESO, pyd. ⊥ MSVC,
  ⊥ Intel. Precedent: SciPy win wheels use rtools = mingw-w64; NumPy doc lists MinGW-w64
  as supported. Sandia's own MSVC path rejected: QUESO not MSVC-clean
  (dakota-packages 5c0356b), needs Intel Fortran, static-lib defaults.
- C.tpls — system TPLs from MSYS2 pacman, direct analog of `yum install` (linux) /
  `brew install` (macos): boost, hdf5, gsl, lapack(+openblas), + msys `patch`/`make`.
- C.scope — cp313 win_amd64 only. ⊥ win32, ⊥ windows-arm64, ⊥ PyPI/test-PyPI.
- C.abi — target python.org CPython (MSVC-built); `numpy`/`h5py` build+runtime deps come
  as prebuilt win wheels; mingw pyd links them via CMake FindPython.
- C.queso — `HAVE_QUESO=ON` target (feature parity). If QUESO blocks mingw → PoC may ship
  `HAVE_QUESO=OFF` w/ §B entry + README note. ? pending first CI configure.
- C.nortk — windows work ⊥ regress linux/macos legs: cibuildwheel sections, repair
  scripts, CMake linux/macos code paths unchanged (additive edits only).
- C.vend — DLL vendoring = `delvewheel` (win analog of auditwheel/delocate) for
  `environment*.pyd`; `dakota.exe` gets needed DLLs staged next to it in the wheel
  (no rpath on Windows; exe dir is first in DLL search order).

## §I Interfaces

- toml: `[tool.cibuildwheel.windows]` + `…windows.environment` → windows build config.
- cmd: `scripts/repair_wheel_windows.py {dest_dir} {wheel}` → repaired wheel in dest_dir.
- ci: job `wheels-windows` → artifact `windows-poc-cp313_win_amd64` (name kept off
  the `wheels-*` glob so publish jobs ⊥ see it, PoC only).
- cmd: `make get-dakota-src` unchanged on unix; runs under msys bash on windows.
- env: CI sets `CIBW_BUILD=cp313-*`, `CIBW_ARCHS=AMD64`.

## §V Invariants

V1kq: ∀ DLL D ∈ imports(`environment*.pyd`) ∖ {`api-ms-win-*`,`ucrt*`,`VCRUNTIME*`,`MSVCP*`}
→ D present in repaired wheel.
V2pn: fresh windows venv + repaired wheel → `dakota --version` rc=0 (exe finds own DLLs).
V3rw: fresh windows venv + repaired wheel → `pytest` rc=0 on windows runner.
V4tx: ∀ windows PR → linux/macos cibuildwheel sections + repair scripts unchanged
(additive-only edits; diff audit).
V5vz: ∀ `src_patches_v624/*` applied identically ∀ platform; mingw-specific hunks behind
`__MINGW32__`/CMake platform guards.
V6bc: windows build matrix yields exactly `cp313-cp313-win_amd64`; ⊥ win32 wheels.
V7df: `release`, `test-pypi`, `pypi` jobs ⊥ consume windows artifacts.

## §T Tasks

id|status|task|cites
T1hk|x|pyproject.toml: add `[tool.cibuildwheel.windows]` (+environment): pacman before-all, ucrt64 PATH/CC/CXX/FC/TPL roots, ccache, skip win32, repair → repair_wheel_windows.py|C.toolchain,C.tpls,I.toml,V6bc
T2jn|x|CMakeLists.txt: collect built `*.dll` TPLs + `libdakota_src.dll` into `.data/scripts` on MINGW (excl `environment*.pyd`, `*.dll.a` import libs); keep unix globs inert|V1kq,C.nortk
T3lp|x|get-dakota-src windows-usable: msys bash path documented/wired in CI (curl+tar+patch via msys); Makefile unix behavior unchanged|C.src,V5vz
T4qs|x|scripts/repair_wheel_windows.py: PATH-stage `.data/scripts` DLLs → `delvewheel repair` for pyd → stage exe DLL closure next to `dakota.exe` → RECORD rewrite → zip verify|V1kq,V2pn,I.cmd,C.vend
T5tv|x|buildwheels.yml: `wheels-windows` job (dakota-src cache, pacman, ccache cache, cibuildwheel cp313/AMD64, wheel integrity, pytest, upload artifact; excluded from release/pypi needs)|V3rw,V6bc,V7df,I.ci
T6wx|.|CI iteration: mingw-port patches into src_patches_v624 as dakota/QUESO configure/compile failures demand|C.src,C.queso,V5vz
T7za|.|README: windows support status once CI green|C.scope
T8rb|x|test portability win32: skipif on fork-interface tests spawning shebang drivers (echo/./driver/rosenbrock); python-callback tests ⊥ skip|V3rw
T9sw|x|TEMP PR scaffolding: buildwheels.yml gates wheels-linux/sbom-scan/dependency-review/wheels-macos/test behind `if: github.ref == 'refs/heads/__windows-poc-disabled__'`; REVERT BEFORE MERGE (restore dep-review's original `if: github.event_name == 'pull_request'`)|C.scope

## §B Bugs

id|date|cause|fix
B1rt|2026-10-01|pacman boost 1.92 has no libboost_regex: Boost.Regex is header-only upstream in 1.92 (`add_library(boost_regex INTERFACE)`; b2 compiles only the 2 C POSIX-API shims) so MSYS2 installs no regex lib, but module-mode FindBoost (forced via Boost_NO_BOOST_CMAKE) demands a real lib per component → dakota configure fails "Could NOT find Boost (missing: regex)" while program_options/serialization resolve fine from pacman's *-mt.a|scripts/build_boost_regex.sh (explicit wheels-windows CI step; before-all has no repo-root cwd on windows) compiles upstream's 2 shims into pacman-named /ucrt64/lib/libboost_regex-mt.a; archive content is link-irrelevant (Dakota's boost::regex use is header-inlined); script pins BOOST_TAG+version assert
B2gh|2026-10-01|`echo C:/msys64/usr/bin >> $GITHUB_PATH` makes every LATER step's `shell: bash` resolve to msys bash (was Git Bash) → GH's bash step protocol (assumes Git Bash) dies: nested `bash.exe -lc` step exited 1 with zero output right after a fully-successful pacman|host msys invocations from pwsh steps via full-path `C:/msys64/usr/bin/bash.exe -lc "..."` (cwd = workspace → relative script paths fine), and place such steps before the PATH prepend; documented at the Materialize libboost_regex step
