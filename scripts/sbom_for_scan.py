#!/usr/bin/env python3
"""Drop SBOM components grype can't meaningfully match (e.g. unversioned numpy), for a dedicated scan-only copy."""

import json
import sys

UNSCANNABLE_REFS = {"pkg:pypi/numpy"}


def main() -> int:
    src, dst = sys.argv[1], sys.argv[2]
    with open(src, encoding="utf-8") as f:
        data = json.load(f)

    data["components"] = [c for c in data["components"] if c["bom-ref"] not in UNSCANNABLE_REFS]

    dependencies = data.get("dependencies", [])
    for dep in dependencies:
        if "dependsOn" in dep:
            dep["dependsOn"] = [ref for ref in dep["dependsOn"] if ref not in UNSCANNABLE_REFS]
    data["dependencies"] = [dep for dep in dependencies if dep["ref"] not in UNSCANNABLE_REFS]

    with open(dst, "w", encoding="utf-8") as f:
        json.dump(data, f)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
