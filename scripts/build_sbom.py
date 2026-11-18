#!/usr/bin/env python3
"""Inventory installed Python requirements with syft; merge/validate one release SBOM."""
import argparse
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from font_sbom import ROOT, ROOT_REF, document, generate
from spec import VERSION


def write(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def requirements_only(bom: dict) -> dict:
    """Keep the actual pinned packages and their discovered transitive dependencies."""
    normalize = lambda name: re.sub(r"[-_.]+", "-", name).lower()
    pins = {}
    for line in (ROOT / "requirements.txt").read_text().splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        match = re.fullmatch(r"([A-Za-z0-9_.-]+)==([^\s#;]+)", line.strip())
        if not match:
            raise ValueError("SBOM requires exact name==version pins in requirements.txt")
        pins[normalize(match[1])] = match[2]
    packages = {c["bom-ref"]: c for c in bom.get("components", []) if c.get("purl", "").startswith("pkg:pypi/")}
    needed = set()
    for name, version in pins.items():
        matches = [ref for ref, c in packages.items()
                   if normalize(c["name"]) == name and c.get("version") == version]
        if len(matches) != 1:
            raise ValueError(f"syft did not find exactly one installed {name}=={version}")
        needed.update(matches)
    edges = {d["ref"]: set(d.get("dependsOn", [])) for d in bom.get("dependencies", [])}
    while True:
        expanded = needed | {ref for parent in needed for ref in edges.get(parent, set())}
        if expanded == needed:
            break
        needed = expanded
    if not needed <= packages.keys():
        raise ValueError("syft dependency graph references a missing Python package")
    selected = [packages[ref] for ref in sorted(needed)]
    for c in selected:
        c.setdefault("properties", []).append({"name": "dokusho:role", "value": "build-dependency"})
    result = document(selected, [{"ref": ref, "dependsOn": sorted(edges.get(ref, set()))}
                                 for ref in sorted(needed)])
    result["metadata"] = {"tools": bom["metadata"]["tools"]}
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--venv", type=Path, default=Path(sys.prefix))
    parser.add_argument("--sources", type=Path, default=ROOT / "sources")
    parser.add_argument("--fonts", type=Path, default=ROOT / "fonts")
    parser.add_argument("--work-dir", type=Path, required=True, help="New directory for intermediate BOMs")
    parser.add_argument("--output", type=Path, default=ROOT / f"fonts/DokushoUD-{VERSION}.cdx.json")
    args = parser.parse_args()
    args.work_dir.mkdir(parents=True, exist_ok=False)
    if args.output.exists():
        raise FileExistsError(f"Refusing to overwrite {args.output}")
    env = {**os.environ, "SYFT_CHECK_FOR_APP_UPDATE": "false",
           "SYFT_FILE_METADATA_SELECTION": "none",
           "SYFT_CACHE_DIR": str(args.work_dir / "syft-cache"),
           "DOTNET_CLI_HOME": str(args.work_dir / "dotnet")}
    raw = args.work_dir / "python-raw.cdx.json"
    subprocess.run(["syft", "scan", f"dir:{args.venv.resolve()}",
                    "--override-default-catalogers", "python-installed-package-cataloger",
                    "--select-catalogers=-file", "--source-name", "DokushoUD-build-dependencies",
                    "--source-version", VERSION, "-o", f"cyclonedx-json@1.6={raw}"], check=True, env=env)
    python = requirements_only(json.loads(raw.read_text()))
    sources, fonts = generate(args.sources, args.fonts, [c["bom-ref"] for c in python["components"]])
    parts = [("python", python), ("sources", sources), ("fonts", fonts)]
    paths = []
    for name, bom in parts:
        path = args.work_dir / f"{name}.cdx.json"
        # The CLI also inserts each input's metadata.component into components.
        # Add the single release subject after merge to avoid duplicating its ID.
        merge_input = bom
        if name == "fonts":
            merge_input = {key: value for key, value in bom.items() if key != "metadata"}
            merge_input["dependencies"] = [d for d in bom["dependencies"] if d["ref"] != ROOT_REF]
        write(path, merge_input)
        paths.append(str(path))
    merged = args.work_dir / "merged.cdx.json"
    subprocess.run(["cyclonedx", "merge", "--input-files", *paths, "--output-file", str(merged),
                    "--output-format", "json", "--output-version", "v1_6"], check=True, env=env)
    result = json.loads(merged.read_text())
    # Flat merge has no primary subject. Restore the release subject and its graph;
    # components themselves must come from cyclonedx merge without loss or dedup surprises.
    expected = {c["bom-ref"] for _, bom in parts for c in bom["components"]}
    actual = [c["bom-ref"] for c in result["components"]]
    if len(actual) != len(expected) or set(actual) != expected:
        raise ValueError("cyclonedx merge changed component identities")
    result["metadata"] = fonts["metadata"]
    result["metadata"]["tools"] = python["metadata"]["tools"]
    cli_version = subprocess.check_output(["cyclonedx", "--version"], env=env, text=True).strip().split("+")[0]
    result["metadata"]["tools"]["components"].append({"type": "application", "name": "cyclonedx-cli",
                                                     "version": cli_version})
    epoch = os.environ.get("SOURCE_DATE_EPOCH")
    timestamp = datetime.fromtimestamp(int(epoch), timezone.utc) if epoch else datetime.now(timezone.utc)
    result["metadata"]["timestamp"] = timestamp.isoformat(timespec="seconds").replace("+00:00", "Z")
    result["dependencies"] = [edge for _, bom in parts for edge in bom["dependencies"]]
    known = expected | {ROOT_REF}
    for edge in result["dependencies"]:
        if edge["ref"] not in known or not set(edge.get("dependsOn", [])) <= known:
            raise ValueError("Dangling SBOM dependency")
    candidate = args.work_dir / "release.cdx.json"
    write(candidate, result)
    subprocess.run(["cyclonedx", "validate", "--input-file", str(candidate), "--fail-on-errors"],
                   check=True, env=env)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as output:
        output.write(candidate.read_text())
    print(f"{args.output}: {len(result['components'])} components; "
          f"{len(result['dependencies'])} dependency records; validated CycloneDX 1.6")


if __name__ == "__main__":
    main()
