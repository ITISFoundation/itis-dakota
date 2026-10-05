#!/usr/bin/env python3
"""Wheel integrity gate for CI (zip CRC check of all built artifacts).

Invoked by the wheels-linux, wheels-macos and wheels-windows jobs (it
replaces three copies of inline Python in buildwheels.yml).

Checks wheelhouse/*.whl by default. A corrupted wheel is swapped from
--safe-dir when a healthy same-named copy exists there: that recovery path
exists because Docker Desktop on the macOS runners intermittently corrupted
wheels via `docker cp` (BadCRC); repair_wheel.sh writes a duplicate through
the project bind-mount at .cibw_wheels_safe/, which virtiofs serves
reliably. On native runners (and Windows) no safe dir exists, so a
corrupted wheel simply fails the gate. Exit code is non-zero if any wheel
is unrecoverably corrupted.
"""

from __future__ import annotations

import argparse
import glob
import os
import shutil
import sys
import zipfile


def _first_bad(path: str) -> str | None:
    """Name of the first corrupted entry (or error text), None if healthy."""
    try:
        with zipfile.ZipFile(path) as zf:
            return zf.testzip()
    except zipfile.BadZipFile as exc:
        return str(exc)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--glob", default="wheelhouse/*.whl")
    ap.add_argument("--safe-dir", default=".cibw_wheels_safe")
    args = ap.parse_args()

    failed = False
    for whl in sorted(glob.glob(args.glob)):
        bad = _first_bad(whl)
        if bad is None:
            with zipfile.ZipFile(whl) as zf:
                print(f"OK: {whl} ({len(zf.namelist())} entries)")
            continue
        print(f"CORRUPTED: {whl} (issue: {bad})", file=sys.stderr)
        safe = os.path.join(args.safe_dir, os.path.basename(whl))
        if os.path.exists(safe) and _first_bad(safe) is None:
            shutil.copyfile(safe, whl)
            print(f"RECOVERED: replaced {whl} from {safe}")
            continue
        if os.path.exists(safe):
            print(f"  safe copy also corrupted: {safe}", file=sys.stderr)
        else:
            print(f"  no safe copy at {safe}", file=sys.stderr)
        failed = True
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
