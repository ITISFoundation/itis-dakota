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
- ci: job `wheels-windows` → artifact `wheels-windows-cp313_win_amd64`.
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
T3lp|.|get-dakota-src windows-usable: msys bash path documented/wired in CI (curl+tar+patch via msys); Makefile unix behavior unchanged|C.src,V5vz
T4qs|.|scripts/repair_wheel_windows.py: PATH-stage `.data/scripts` DLLs → `delvewheel repair` for pyd → stage exe DLL closure next to `dakota.exe` → RECORD rewrite → zip verify|V1kq,V2pn,I.cmd,C.vend
T5tv|.|buildwheels.yml: `wheels-windows` job (dakota-src cache, pacman, ccache cache, cibuildwheel cp313/AMD64, wheel integrity, pytest, upload artifact; excluded from release/pypi needs)|V3rw,V6bc,V7df,I.ci
T6wx|.|CI iteration: mingw-port patches into src_patches_v624 as dakota/QUESO configure/compile failures demand|C.src,C.queso,V5vz
T7za|.|README: windows support status once CI green|C.scope

## §B Bugs

id|date|cause|fix
