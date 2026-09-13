#!/usr/bin/env python3
"""Cyclomatic-complexity budget gate for zc.buildout.

Compares a fresh `radon cc` scan of src/zc/buildout against the
checked-in baseline (etc/complexity-baseline.json):

- a function or method more complex than its baseline entry fails;
- a function or method with no baseline entry must be grade B or
  better (CC <= NEW_MAX_CC);
- entries that got simpler or disappeared are reported as progress.

After landing an accepted simplification, refresh the baseline with
`make complexity-baseline` and commit the result.

radon must be on PATH (the devenv provides it). Stdlib-only, py39+.
"""
import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
BASELINE = REPO / "etc" / "complexity-baseline.json"
SOURCE = "src/zc/buildout"
NEW_MAX_CC = 10  # radon grade B ceiling for code without a baseline entry


def scan():
    out = subprocess.run(
        ["radon", "cc", SOURCE, "--exclude", "*/tests/*", "-j"],
        cwd=str(REPO), capture_output=True, text=True, check=True,
    ).stdout
    blocks = {}
    for path, entries in json.loads(out).items():
        for entry in entries:
            if entry["type"] == "class":
                items = [
                    dict(m, classname=entry["name"])
                    for m in entry.get("methods", [])
                ]
            else:
                items = [entry]
            for item in items:
                parts = [item.get("classname"), item["name"]]
                key = "{}:{}".format(path, ".".join(p for p in parts if p))
                if key in blocks:  # same-named siblings: disambiguate
                    key = "{}@L{}".format(key, item["lineno"])
                blocks[key] = item["complexity"]
    return blocks


def main(argv):
    current = scan()
    if "--write-baseline" in argv:
        BASELINE.write_text(
            json.dumps(current, indent=1, sort_keys=True) + "\n"
        )
        print("wrote {} ({} blocks)".format(BASELINE, len(current)))
        return 0

    baseline = json.loads(BASELINE.read_text())
    failures = []
    for key, cc in sorted(current.items()):
        if key in baseline:
            if cc > baseline[key]:
                failures.append(
                    "{}: CC {} exceeds baseline {}".format(key, cc, baseline[key])
                )
            elif cc < baseline[key]:
                print("improved: {} CC {} -> {} (refresh the baseline)".format(
                    key, baseline[key], cc))
        elif cc > NEW_MAX_CC:
            failures.append(
                "{}: new code CC {} exceeds grade B ceiling {}".format(
                    key, cc, NEW_MAX_CC))
    for key in sorted(set(baseline) - set(current)):
        print("gone: {} (refresh the baseline)".format(key))

    if failures:
        print("\ncomplexity gate FAILED:", file=sys.stderr)
        for line in failures:
            print("  " + line, file=sys.stderr)
        return 1
    print("complexity gate OK: {} blocks within budget".format(len(current)))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
