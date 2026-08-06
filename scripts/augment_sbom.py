#!/usr/bin/env python3
"""Add numpy and the vendored Dakota/Pecos/Surfpack/dakota-packages sources to the wheel's embedded auditwheel SBOM, in place."""

import argparse
import json
import subprocess
import sys
import zipfile
from pathlib import Path

SBOM_MEMBER_GLOB = "*.dist-info/sboms/auditwheel.cdx.json"

VENDORED_SOURCES = [
    {"name": "dakota", "path": "dakota", "type": "application"},
    {"name": "pecos", "path": "dakota/packages/pecos", "type": "library"},
    {"name": "surfpack", "path": "dakota/packages/surfpack", "type": "library"},
    {"name": "dakota-packages", "path": "dakota/packages/external", "type": "library"},
]


def git(repo_path: Path, *args: str) -> str | None:
    try:
        out = subprocess.run(
            ["git", "-C", str(repo_path), *args],
            capture_output=True,
            text=True,
            check=True,
        )
        return out.stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None


def owner_repo_from_remote(url: str) -> tuple[str, str] | None:
    url = url.removesuffix(".git")
    for sep in ("github.com/", "github.com:"):
        if sep in url:
            owner, _, repo = url.partition(sep)[2].partition("/")
            if owner and repo:
                return owner, repo
    return None


def vendored_source_component(name: str, path: str, comp_type: str, repo_root: Path) -> dict | None:
    repo_path = repo_root / path
    commit = git(repo_path, "rev-parse", "HEAD")
    remote_url = git(repo_path, "remote", "get-url", "origin")
    if not commit or not remote_url:
        print(f"augment_sbom: skipping {name} (no git metadata at {repo_path})", file=sys.stderr)
        return None

    owner_repo = owner_repo_from_remote(remote_url)
    version = git(repo_path, "describe", "--tags", "--always") or commit[:12]
    bom_ref = (
        f"pkg:github/{owner_repo[0]}/{owner_repo[1]}@{commit}"
        if owner_repo
        else f"pkg:generic/{name}@{commit}"
    )
    return {
        "type": comp_type,
        "bom-ref": bom_ref,
        "name": name,
        "version": version,
        "purl": bom_ref,
        "description": f"Statically linked into itis_dakota, source: {remote_url}",
        "externalReferences": [{"type": "vcs", "url": remote_url}],
    }


def numpy_component() -> dict | None:
    try:
        import numpy
    except ImportError:
        print("augment_sbom: skipping numpy (not importable)", file=sys.stderr)
        return None

    version = numpy.__version__
    bom_ref = f"pkg:pypi/numpy@{version}"
    return {
        "type": "library",
        "bom-ref": bom_ref,
        "name": "numpy",
        "version": version,
        "purl": bom_ref,
        "scope": "required",
    }


def augment(data: dict, repo_root: Path) -> dict:
    root_ref = data["metadata"]["component"]["bom-ref"]
    existing_refs = {c["bom-ref"] for c in data["components"]}

    new_components = [numpy_component()]
    for source in VENDORED_SOURCES:
        new_components.append(
            vendored_source_component(source["name"], source["path"], source["type"], repo_root)
        )
    new_components = [c for c in new_components if c and c["bom-ref"] not in existing_refs]

    data["components"].extend(new_components)

    dependencies = data.setdefault("dependencies", [])
    dep_by_ref = {d["ref"]: d for d in dependencies}
    root_dep = dep_by_ref.get(root_ref)
    if root_dep is None:
        root_dep = {"ref": root_ref, "dependsOn": []}
        dependencies.append(root_dep)
    root_depends_on = set(root_dep.setdefault("dependsOn", []))

    for component in new_components:
        root_depends_on.add(component["bom-ref"])
        if component["bom-ref"] not in dep_by_ref:
            dependencies.append({"ref": component["bom-ref"]})
    root_dep["dependsOn"] = sorted(root_depends_on)

    data["metadata"].setdefault("tools", []).append(
        {"name": "itis-dakota-augment-sbom", "version": "1.0"}
    )
    return data


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--wheel", required=True, type=Path, help="Path to the .whl file to augment in place")
    parser.add_argument("--repo-root", required=True, type=Path, help="Path to the itis-dakota checkout")
    args = parser.parse_args()

    with zipfile.ZipFile(args.wheel) as zin:
        sbom_names = [n for n in zin.namelist() if Path(n).match(SBOM_MEMBER_GLOB)]
        if not sbom_names:
            print(f"augment_sbom: no auditwheel SBOM found in {args.wheel}, skipping", file=sys.stderr)
            return 0
        sbom_name = sbom_names[0]
        infos = zin.infolist()
        contents = {info.filename: zin.read(info.filename) for info in infos}

    data = json.loads(contents[sbom_name])
    data = augment(data, args.repo_root)
    contents[sbom_name] = json.dumps(data).encode()

    tmp_wheel = args.wheel.with_suffix(".whl.tmp")
    with zipfile.ZipFile(tmp_wheel, "w") as zout:
        for info in infos:
            zout.writestr(info, contents[info.filename])
    tmp_wheel.replace(args.wheel)

    print(f"augment_sbom: added {len(data['components'])} total components to {sbom_name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
