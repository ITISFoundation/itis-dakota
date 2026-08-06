#!/usr/bin/env python3
"""Convert the wheel's embedded CycloneDX SBOM into a snapshot and submit it to GitHub's dependency graph."""

import datetime
import json
import os
import sys
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

SBOM_MEMBER_GLOB = "*.dist-info/sboms/auditwheel.cdx.json"


def load_sbom(wheel_path: Path) -> dict:
    with zipfile.ZipFile(wheel_path) as zf:
        names = [n for n in zf.namelist() if Path(n).match(SBOM_MEMBER_GLOB)]
        if not names:
            raise SystemExit(f"No SBOM found in {wheel_path}")
        return json.loads(zf.read(names[0]))


def build_manifest(sbom: dict) -> dict:
    root_ref = sbom["metadata"]["component"]["bom-ref"]
    components_by_ref = {c["bom-ref"]: c for c in sbom["components"]}
    root_deps = next(
        (d["dependsOn"] for d in sbom.get("dependencies", []) if d["ref"] == root_ref),
        [],
    )

    resolved = {}
    for ref in root_deps:
        component = components_by_ref.get(ref)
        if component is None or "purl" not in component:
            continue
        resolved[component["name"]] = {
            "package_url": component["purl"],
            "relationship": "direct",
            "scope": "runtime",
        }
    return resolved


def submit(repo: str, token: str, payload: dict) -> None:
    req = urllib.request.Request(
        f"https://api.github.com/repos/{repo}/dependency-graph/snapshots",
        data=json.dumps(payload).encode(),
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req) as resp:
            print(f"submit_sbom_snapshot: {resp.status} {resp.read().decode()}")
    except urllib.error.HTTPError as exc:
        print(f"submit_sbom_snapshot: {exc.code} {exc.read().decode()}", file=sys.stderr)
        raise


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: submit_sbom_snapshot.py <wheel-path>", file=sys.stderr)
        return 1

    wheel_path = Path(sys.argv[1])
    sbom = load_sbom(wheel_path)
    resolved = build_manifest(sbom)

    repo = os.environ["GITHUB_REPOSITORY"]
    token = os.environ["GITHUB_TOKEN"]
    manifest_name = wheel_path.name

    payload = {
        "version": 0,
        "sha": os.environ["GITHUB_SHA"],
        "ref": os.environ["GITHUB_REF"],
        "job": {
            "correlator": f"{os.environ.get('GITHUB_WORKFLOW', 'buildwheels')}_sbom-submission",
            "id": os.environ.get("GITHUB_RUN_ID", "0"),
        },
        "detector": {
            "name": "itis-dakota-augment-sbom",
            "version": "1.0",
            "url": "https://github.com/ITISFoundation/itis-dakota",
        },
        "scanned": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "manifests": {
            manifest_name: {
                "name": manifest_name,
                "resolved": resolved,
            }
        },
    }

    submit(repo, token, payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
