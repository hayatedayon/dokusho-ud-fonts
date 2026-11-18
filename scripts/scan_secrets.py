#!/usr/bin/env python3
"""Scan the working tree and event commit range; --all-history audits every ref."""
import argparse
import json
import os
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SHA = re.compile(r"[0-9a-f]{40}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--all-history", action="store_true")
    args = parser.parse_args()
    common = ["--config", str(ROOT / ".betterleaks.toml"), "--redact=100", "--no-banner",
              "--ignore-gitleaks-allow"]
    # No live credential validation: findings never go to third-party APIs.
    subprocess.run(["betterleaks", "dir", str(ROOT), *common], check=True, cwd=ROOT)
    log_opts = "--all --full-history"
    if not args.all_history and os.environ.get("GITHUB_EVENT_PATH"):
        event = json.loads(Path(os.environ["GITHUB_EVENT_PATH"]).read_text())
        name = os.environ.get("GITHUB_EVENT_NAME")
        if name == "push":
            before, after = event.get("before", ""), event.get("after", "")
            if SHA.fullmatch(after) and after != "0" * 40:
                # A new branch has no before SHA: scan all commits reachable from after.
                log_opts = after
                if SHA.fullmatch(before) and before != "0" * 40:
                    # After a force push the old tip might no longer be in the clone.
                    if subprocess.run(["git", "cat-file", "-e", before], cwd=ROOT,
                                      stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode:
                        subprocess.run(["git", "fetch", "--no-tags", "origin", before],
                                       check=True, cwd=ROOT)
                    log_opts = f"{before}..{after}"
        elif name == "pull_request":
            base = event["pull_request"]["base"]["sha"]
            head = event["pull_request"]["head"]["sha"]
            if not SHA.fullmatch(base) or not SHA.fullmatch(head):
                raise ValueError("Invalid pull request commit IDs")
            log_opts = f"{base}..{head}"
    subprocess.run(["betterleaks", "git", str(ROOT), "--log-opts", log_opts, *common],
                   check=True, cwd=ROOT)


if __name__ == "__main__":
    main()
