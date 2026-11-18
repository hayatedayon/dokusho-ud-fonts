#!/usr/bin/env python3
"""Install pinned official Linux x86-64 tools, verifying SHA-256 before use."""
import argparse
import hashlib
import io
import json
import platform
import tarfile
import urllib.request
from pathlib import Path


def fetch(url: str, digest: str, destination: Path) -> bytes:
    if destination.exists():
        data = destination.read_bytes()
    else:
        request = urllib.request.Request(url, headers={"User-Agent": "dokusho-ud-tools"})
        with urllib.request.urlopen(request, timeout=120) as response:
            data = response.read()
        if hashlib.sha256(data).hexdigest() != digest:
            raise ValueError(f"SHA-256 mismatch: {url}")
        with destination.open("xb") as output:
            output.write(data)
    if hashlib.sha256(data).hexdigest() != digest:
        raise ValueError(f"SHA-256 mismatch: {destination}")
    return data


def main() -> None:
    manifest = json.loads(Path(__file__).with_name("supply_chain_tools.json").read_text())
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("tools", nargs="+", choices=sorted(manifest))
    parser.add_argument("--bin-dir", type=Path, required=True)
    parser.add_argument("--download-dir", type=Path, required=True)
    args = parser.parse_args()
    if platform.system() != "Linux" or platform.machine() not in {"x86_64", "AMD64"}:
        parser.error("These pinned assets support Linux x86-64 only; use a Linux worktree/container.")
    args.bin_dir.mkdir(parents=True, exist_ok=True)
    args.download_dir.mkdir(parents=True, exist_ok=True)
    for tool in args.tools:
        pin = manifest[tool]
        filename = pin["url"].rsplit("/", 1)[1]
        data = fetch(pin["url"], pin["sha256"], args.download_dir / filename)
        if "checksums_url" in pin:
            checksums = fetch(pin["checksums_url"], pin["checksums_sha256"],
                              args.download_dir / f"{tool}-checksums.txt").decode()
            listed = {line.split()[-1].lstrip("*"): line.split()[0]
                      for line in checksums.splitlines() if len(line.split()) == 2}
            if listed.get(filename) != pin["sha256"]:
                raise ValueError(f"Official checksum does not match pin: {tool}")
        if filename.endswith(".tar.gz"):
            with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as archive:
                members = [m for m in archive.getmembers()
                           if m.isfile() and Path(m.name).name == pin["binary"]]
                if len(members) != 1:
                    raise ValueError(f"Expected one binary in {filename}")
                data = archive.extractfile(members[0]).read()
        destination = args.bin_dir / pin["binary"]
        if destination.exists():
            if destination.read_bytes() != data:
                raise ValueError(f"Refusing to overwrite existing binary: {destination}")
        else:
            with destination.open("xb") as output:
                output.write(data)
            destination.chmod(0o755)
        print(f"{tool} {pin['version']}: verified {pin['sha256']}")


if __name__ == "__main__":
    main()
