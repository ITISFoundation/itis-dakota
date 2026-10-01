#!/usr/bin/env python3
"""Windows wheel repair for itis-dakota (Windows analog of repair_wheel.sh).

Two duties, mirroring what auditwheel does on Linux:

1. ``delvewheel repair`` vendors every DLL that ``environment*.pyd`` needs
   (mingw-built Boost/HDF5/GSL/OpenBLAS plus libgcc/libstdc++/libgfortran/
   libwinpthread from MSYS2 ucrt64, plus the mingw-built TPL DLLs and
   libdakota_src.dll staged in ``*.data/scripts``) into ``itis_dakota.libs``
   and rewrites the pyd's import table to load them from there.

2. delvewheel only understands extension modules, so ``dakota.exe`` is handled
   here: Windows has no rpath and a program's own directory is the first DLL
   search location, so we compute the exe's DLL dependency closure (skipping
   DLLs present in System32) and stage the closure as sibling files inside
   ``*.data/scripts``, which pip installs into the venv ``Scripts`` directory.

RECORD is fully regenerated afterwards, and the result is zip-verified.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import os
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

import pefile

MSYS_UCRT64_BIN = r"C:\msys64\ucrt64\bin"


def dll_imports(pe_path: Path) -> set[str]:
    """Direct DLL import names of a PE file, lowercased."""
    pe = pefile.PE(str(pe_path), fast_load=True)
    try:
        pe.parse_data_directories(
            directories=[pefile.DIRECTORY_ENTRY["IMAGE_DIRECTORY_ENTRY_IMPORT"]]
        )
        if not hasattr(pe, "DIRECTORY_ENTRY_IMPORT"):
            return set()
        return {e.dll.decode(errors="ignore").lower() for e in pe.DIRECTORY_ENTRY_IMPORT}
    finally:
        pe.close()


def is_system_dll(name: str) -> bool:
    """A DLL that Windows itself provides (never vendored)."""
    if name.startswith(("api-ms-", "ext-ms-")):
        return True
    sys32 = Path(os.environ.get("WINDIR", r"C:\Windows")) / "System32"
    return (sys32 / name).exists()


def repair_with_delvewheel(wheel: Path, dest_dir: Path, extra_path: list[str]) -> Path:
    env = dict(os.environ)
    env["PATH"] = os.pathsep.join(extra_path + [env.get("PATH", "")])
    subprocess.run(
        [sys.executable, "-m", "delvewheel", "repair", "-w", str(dest_dir), str(wheel)],
        check=True,
        env=env,
    )
    repaired = dest_dir / wheel.name
    if not repaired.exists():
        raise SystemExit(f"delvewheel did not produce {repaired}")
    return repaired


def stage_exe_dlls(wheel_path: Path) -> None:
    """Copy the dakota.exe DLL closure next to the exe inside the wheel."""
    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        with zipfile.ZipFile(wheel_path) as zf:
            zf.extractall(td_path)

        exe = next(
            (p for p in td_path.rglob("*.data/scripts/dakota.exe")),
            None,
        )
        if exe is None:
            raise SystemExit("dakota.exe not found in wheel *.data/scripts")
        scripts_dir = exe.parent

        # Candidate DLL pool: everything delvewheel vendored + everything
        # already staged in the scripts dir. Vendored copies are mangled
        # (name-8hex.dll), so also index them under the pre-mangle name the
        # exe actually imports; originals win over mangled copies.
        pool: dict[str, Path] = {}

        def _pool_add(dll: Path) -> None:
            key = dll.name.lower()
            base = re.sub(r"-[0-9a-f]{8,16}$", "", dll.stem.lower())
            pool.setdefault(key, dll)
            if base != dll.stem.lower():
                pool.setdefault(base + ".dll", dll)

        all_dlls = list(td_path.rglob("*.dll"))
        for dll in sorted(d for d in all_dlls if "-" not in d.stem.lower()):
            _pool_add(dll)
        for dll in sorted(all_dlls):
            _pool_add(dll)

        staged = 0
        work = list(dll_imports(exe))
        seen: set[str] = set()
        missing: set[str] = set()
        while work:
            name = work.pop().lower()
            if name in seen or is_system_dll(name):
                continue
            seen.add(name)
            src = pool.get(name)
            if src is None:
                missing.add(name)
                continue
            # Stage under the IMPORT name (src may carry a delvewheel-mangled
            # file name the loader will never look for next to the exe).
            target = scripts_dir / name
            if not target.exists():
                shutil.copyfile(src, target)
                staged += 1
            work.extend(dll_imports(src))

        if missing:
            # mingw-built DLLs that delvewheel failed to vendor are real
            # breakage at runtime; anything else is presumed a false alarm.
            mingw_style = {m for m in missing if m.startswith("lib")}
            if mingw_style:
                raise SystemExit(
                    f" dakota.exe needs DLLs not found in wheel: {sorted(mingw_style)}"
                )
            print(f"warning: treating unresolved imports as system DLLs: {sorted(missing)}")

        rewrite_record(td_path)
        rezip(wheel_path, td_path)
        print(f"staged {staged} DLL(s) next to dakota.exe in {wheel_path.name}")


def rewrite_record(root: Path) -> None:
    dist_info = next(root.glob("*.dist-info"))
    lines = []
    for p in sorted(root.rglob("*")):
        if not p.is_file():
            continue
        rel = p.relative_to(root).as_posix()
        if p.parent == dist_info and p.name == "RECORD":
            lines.append(f"{rel},,")
            continue
        data = p.read_bytes()
        digest = base64.urlsafe_b64encode(hashlib.sha256(data).digest()).rstrip(b"=")
        lines.append(f"{rel},sha256={digest.decode()},{len(data)}")
    (dist_info / "RECORD").write_text("\n".join(lines) + "\n", newline="\n")


def rezip(wheel_path: Path, root: Path) -> None:
    tmp = wheel_path.with_suffix(".tmp.whl")
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as zf:
        for p in sorted(root.rglob("*")):
            if p.is_file():
                zf.write(p, p.relative_to(root).as_posix())
    tmp.replace(wheel_path)


def verify_zip(wheel_path: Path) -> None:
    with zipfile.ZipFile(wheel_path) as zf:
        bad = zf.testzip()
        if bad:
            raise SystemExit(f"corrupted wheel entry: {bad}")
        print(f"zip verification passed for {wheel_path.name}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("dest_dir")
    ap.add_argument("wheel")
    args = ap.parse_args()

    wheel = Path(args.wheel).resolve()
    dest_dir = Path(args.dest_dir).resolve()
    dest_dir.mkdir(parents=True, exist_ok=True)

    extra_path = [MSYS_UCRT64_BIN]

    # Stage the mingw-built TPL/libdakota_src DLLs from the pre-repair wheel
    # onto PATH so delvewheel can resolve them (analog of the LD_LIBRARY_PATH
    # dance in repair_wheel.sh).
    scratch = Path(tempfile.mkdtemp())
    try:
        with zipfile.ZipFile(wheel) as zf:
            names = [n for n in zf.namelist() if re.search(r"\.data/scripts/.*\.dll$", n)]
            zf.extractall(scratch, members=names)
        staged = [p.parent for p in scratch.rglob("*.dll")]
        extra_path += [str(p) for p in set(staged)]
        repaired = repair_with_delvewheel(wheel, dest_dir, extra_path)
    finally:
        shutil.rmtree(scratch, ignore_errors=True)

    stage_exe_dlls(repaired)
    verify_zip(repaired)


if __name__ == "__main__":
    main()
