#!/usr/bin/env python3
"""Windows wheel repair for itis-dakota (Windows analog of repair_wheel.sh).

Two duties, mirroring what auditwheel does on Linux:

1. ``delvewheel repair`` vendors every DLL that ``environment*.pyd`` needs
   (mingw-built Boost/HDF5/GSL/OpenBLAS plus libgcc/libstdc++/libgfortran/
   libwinpthread from MSYS2 ucrt64, plus the mingw-built TPL DLLs and
   libdakota_src.dll staged in ``*.data/scripts``) into ``itis_dakota.libs``
   with MANGLED names (the anti-DLL-hell default, required for a published
   wheel). mingw PEs carry a COFF symtab overlay and GNU ld packs import
   name strings with no slack; delvewheel can only mangle a dependent once
   its overlay is gone (it then appends a section for the longer names).
   So we first pre-strip every PE in the wheel (and its staged copies on
   the search PATH) with the MSYS2 GNU strip, and also pass ``--strip`` as
   a fallback for anything else with an overlay. Stripping also shrinks
   the wheel dramatically (unstripped mingw PEs blew the artifact up to
   ~90 MB vs ~34 MB on linux; PyPI's default per-file limit is 60 MB).

2. delvewheel only understands extension modules, so ``dakota.exe`` is handled
   here: Windows has no rpath and a program's own directory is the first DLL
   search location, so we compute the exe's DLL dependency closure (skipping
   DLLs present in System32) and stage the closure as sibling files inside
   ``*.data/scripts``, which pip installs into the venv ``Scripts`` directory.
   The exe is never rewritten by delvewheel, so its closure keeps the bare
   import names; vendored (mangled) copies are indexed under their pre-mangle
   names so the closure resolves either way.

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


def strip_pe(path: Path) -> bool:
    """Run GNU ``strip -s`` over one PE file (removes symtab/debug info and,
    for mingw links, the COFF symtab file overlay). Returns True on success."""
    strip_bin = Path(MSYS_UCRT64_BIN) / "strip.exe"
    if not strip_bin.exists():
        strip_bin = Path("strip")  # fall back to PATH
    try:
        subprocess.run([str(strip_bin), "-s", str(path)], check=True)
        return True
    except (OSError, subprocess.CalledProcessError) as exc:
        print(f"warning: strip failed on {path.name}: {exc}")
        return False


def prestrip_wheel(wheel: Path, dest_dir: Path) -> Path:
    """Strip every exe/dll/pyd inside the wheel before delvewheel runs.

    Two reasons, both product-quality: (a) delvewheel can only mangle a
    dependent once its PE overlay is gone (GNU ld's COFF symtab overlay is
    exactly what blocked B25), and (b) unstripped mingw PEs put the wheel
    over PyPI's default 60 MB per-file limit. Returns the stripped wheel's
    path (the input file is left untouched)."""
    out = dest_dir / wheel.name
    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        with zipfile.ZipFile(wheel) as zf:
            zf.extractall(td_path)
        pes = [
            p
            for p in td_path.rglob("*")
            if p.suffix.lower() in {".exe", ".dll", ".pyd"}
        ]
        stripped = 0
        for pe in pes:
            before = pe.stat().st_size
            if strip_pe(pe):
                stripped += before - pe.stat().st_size
        rewrite_record(td_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
            for p in sorted(td_path.rglob("*")):
                if p.is_file():
                    zf.write(p, p.relative_to(td_path).as_posix())
        print(
            f"pre-stripped {len(pes)} PE files"
            f" ({stripped / 1048576:.1f} MiB smaller) -> {out.name}"
        )
    return out


def repair_with_delvewheel(wheel: Path, dest_dir: Path, extra_path: list[str]) -> Path:
    env = dict(os.environ)
    env["PATH"] = os.pathsep.join(extra_path + [env.get("PATH", "")])
    # Default name mangling ON (published-wheel hygiene: vendored DLLs get
    # hash-suffixed names so no package ever binds another's bare-name DLL).
    # --strip lets delvewheel itself strip any dependent whose overlay blocks
    # mangling (our own PEs were already pre-stripped; this covers the rest);
    # GNU strip resolves via MSYS_UCRT64_BIN prepended above.
    subprocess.run(
        [
            sys.executable,
            "-m",
            "delvewheel",
            "repair",
            "--strip",
            "-w",
            str(dest_dir),
            str(wheel),
        ],
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
            # delvewheel's mangle hash length has moved across versions
            # (8 -> 32 hex chars), so tolerate any hex suffix >= 8.
            base = re.sub(r"-[0-9a-f]{8,64}$", "", dll.stem.lower())
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
            # A venv's Python DLLs (python3.dll / python3XX.dll / free-threaded
            # t-variants) are deliberately NOT vendored: the venv's Scripts
            # directory supplies them beside dakota.exe at runtime (they live
            # next to python.exe, not in System32, so is_system_dll cannot
            # excuse them). Anything else unresolved is real breakage —
            # third-party DLLs without the mingw lib* prefix (zlib1.dll, ...)
            # must not slip through the guard (Copilot review, B30 round).
            # Current artifacts import none of these (green run staged 29 DLLs
            # with an empty missing set), so this allowance never masks them.
            tolerated = {m for m in missing if re.fullmatch(r"python\d{1,3}t?\.dll", m)}
            hard = missing - tolerated
            if hard:
                raise SystemExit(
                    f" dakota.exe needs DLLs not found in wheel: {sorted(hard)}"
                )
            if tolerated:
                print(f"note: venv-provided python DLL imports: {sorted(tolerated)}")

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

    # Stage the mingw-built TPL/libdakota_src DLLs from the PRE-STRIPPED wheel
    # onto PATH so delvewheel can resolve (and vendor the stripped, mangleable
    # copies) — analog of the LD_LIBRARY_PATH dance in repair_wheel.sh.
    scratch = Path(tempfile.mkdtemp())
    try:
        prestripped = prestrip_wheel(wheel, scratch)
        with zipfile.ZipFile(prestripped) as zf:
            names = [n for n in zf.namelist() if re.search(r"\.data/scripts/.*\.dll$", n)]
            zf.extractall(scratch, members=names)
        staged = [p.parent for p in scratch.rglob("*.dll")]
        extra_path += [str(p) for p in set(staged)]
        repaired = repair_with_delvewheel(prestripped, dest_dir, extra_path)
    finally:
        shutil.rmtree(scratch, ignore_errors=True)

    stage_exe_dlls(repaired)
    verify_zip(repaired)


if __name__ == "__main__":
    main()
