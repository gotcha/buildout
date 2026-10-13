"""Write the flag-gated buildout-eggs.pth into the venv's site-packages.

xdist workers — and any other bare venv-python subprocesses the suites
or external pytest tooling (fest's worker pool, mutmut-style runners)
spawn — do not inherit bin/py's baked sys.path, and execnet's spawn
mechanics (-u -c) leave no interpreter option to deliver it. So the
bin/test build refreshes a single .pth import line in the venv: when
ZC_BUILDOUT_SUITE_EGGS is set, the interpreter extends sys.path with
every checkout-rooted entry of bin/py's path (src/, eggs/v5/*.egg,
...). Without the flag the line costs one dict lookup and does
nothing; interpreters outside this venv never see the file, so
spawned pip/build children (python -m build fixtures) stay clean
however the flag is set. Regenerated on every bin/test rebuild, so a
changed egg set self-heals; writing is idempotent.

Run as a Makefile step: bin/py etc/write-buildout-eggs-pth.py
"""

import os
import sys
import sysconfig

FLAG_VAR = "ZC_BUILDOUT_SUITE_EGGS"
PTH_NAME = "buildout-eggs.pth"


def script_dir() -> str:
    return os.path.dirname(os.path.abspath(__file__))


def checkout_root() -> str:
    return os.path.dirname(script_dir())


def suite_paths() -> list[str]:
    """Checkout-rooted absolute entries of the running (bin/py) sys.path."""
    root = os.path.normcase(checkout_root()) + os.sep
    own_dir = os.path.normcase(script_dir()) + os.sep
    seen: set[str] = set()
    paths: list[str] = []
    for entry in sys.path:
        if not entry or not os.path.isabs(entry):
            continue
        abspath = os.path.abspath(entry)
        normed = os.path.normcase(abspath) + os.sep
        if not normed.startswith(root) or normed.startswith(own_dir):
            continue
        if normed not in seen:
            seen.add(normed)
            paths.append(abspath)
    return paths


def pth_line(paths: list[str]) -> str:
    # One .pth import line; must stay exception-free in every interpreter
    # on this venv: a defaulted environ lookup, no I/O, no raises.
    return (
        f"import os,sys; os.environ.get({FLAG_VAR!r}) and "
        f"sys.path.extend([p for p in {paths!r} if p not in sys.path])\n"
    )


def main() -> None:
    paths = suite_paths()
    target = os.path.join(sysconfig.get_path("purelib"), PTH_NAME)
    line = pth_line(paths)
    if os.path.exists(target):
        with open(target, encoding="utf-8") as existing:
            if existing.read() == line:
                print(f"{PTH_NAME}: up to date ({len(paths)} paths)")
                return
    with open(target, "w", encoding="utf-8", newline="\n") as pth:
        pth.write(line)
    print(f"{PTH_NAME}: wrote {len(paths)} paths, gated on {FLAG_VAR}")


if __name__ == "__main__":
    main()
