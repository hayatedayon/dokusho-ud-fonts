#!/usr/bin/env python3
"""Describe source fonts and the eight distributed files as CycloneDX 1.6."""
import hashlib
import json
from pathlib import Path

from fontTools.ttLib import TTFont

from spec import FAMILIES, REPOSITORY, VERSION, WEIGHTS

ROOT = Path(__file__).resolve().parent.parent
ROOT_REF = "dokusho:release:" + VERSION


def document(components: list, dependencies: list) -> dict:
    return {"$schema": "http://cyclonedx.org/schema/bom-1.6.schema.json",
            "bomFormat": "CycloneDX", "specVersion": "1.6", "version": 1,
            "components": components, "dependencies": dependencies}


def component(path: Path, ref: str, version: str, role: str) -> dict:
    return {"type": "file", "bom-ref": ref, "name": path.name, "version": version,
            "hashes": [{"alg": "SHA-256", "content": hashlib.sha256(path.read_bytes()).hexdigest()}],
            "licenses": [{"license": {"id": "OFL-1.1"}}],
            "properties": [{"name": "dokusho:role", "value": role}]}


def generate(sources: Path, fonts: Path, python_refs: list[str]) -> tuple[dict, dict]:
    manifest = json.loads((ROOT / "scripts/sources.json").read_text())
    upstream = []
    for name, entry in sorted(manifest["files"].items()):
        path = sources / name
        ref = f"dokusho:source:{manifest['commit']}:{name}"
        item = component(path, ref, "", "source-font")
        if item["hashes"][0]["content"] != entry["sha256"]:
            raise ValueError(f"Source SHA-256 mismatch: {name}")
        with TTFont(path) as font:
            item["version"] = font["name"].getDebugName(5)
        item["properties"].append({"name": "dokusho:source-commit", "value": manifest["commit"]})
        item["externalReferences"] = [
            {"type": "distribution", "url": manifest["repository"].replace(
                "https://github.com/", "https://raw.githubusercontent.com/") +
             f"/{manifest['commit']}/{entry['path']}"},
            {"type": "vcs", "url": f"{manifest['repository']}/blob/{manifest['commit']}/{entry['path']}"}]
        upstream.append(item)
    source_refs = {item["name"]: item["bom-ref"] for item in upstream}
    outputs, relationships = [], []
    for family in FAMILIES:
        for weight in WEIGHTS:
            parents = [source_refs[f"{family[key]}-{weight}.ttf"] for key in ("ud", "udp")]
            for extension in ("ttf", "woff2"):
                path = fonts / f"{family['postscript']}-{weight}.{extension}"
                ref = "dokusho:font:" + path.name
                item = component(path, ref, VERSION, "distribution")
                item["mime-type"] = "font/" + extension
                with TTFont(path) as font:
                    if not font["name"].getDebugName(5).startswith(f"Version {VERSION};"):
                        raise ValueError(f"Output version mismatch: {path.name}")
                outputs.append(item)
                inputs = parents + python_refs
                if extension == "woff2":
                    inputs = inputs + ["dokusho:font:" + path.with_suffix(".ttf").name]
                relationships.append({"ref": ref, "dependsOn": sorted(inputs)})
    relationships.append({"ref": ROOT_REF, "dependsOn": sorted(c["bom-ref"] for c in outputs)})
    distribution = document(outputs, relationships)
    distribution["metadata"] = {"component": {
        "type": "application", "bom-ref": ROOT_REF, "name": "DokushoUD", "version": VERSION,
        "licenses": [{"license": {"id": "OFL-1.1"}}],
        "externalReferences": [{"type": "vcs", "url": REPOSITORY}],
        "properties": [{"name": "dokusho:dependency-meaning", "value":
                        "Font dependsOn edges describe build inputs; Python packages are not runtime font dependencies."}]}}
    return document(upstream, [{"ref": c["bom-ref"], "dependsOn": []} for c in upstream]), distribution
