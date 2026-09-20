#!/usr/bin/env python3
"""Bump the CI version matrices to the latest releases, on demand.

Run from anywhere: ``python3 etc/bump_ci_versions.py`` (stdlib only).
Re-runnable by design: every run resolves the newest eligible upstream
release per axis -- setuptools, pip, python, uv -- and, when the
matrices lack it, adds it to both workflow files (run-tests.yml and
test-uv.yml), to the dagger job table (dagger/src/buildout_ci/jobs.py),
and to the drift-test counts (dagger/tests/test_jobs.py), so the tree
stays self-consistent per the drift harness's contract. Nothing in the
script keys on a specific current version: constraints are parsed from
setup.py and the targets are found by structural anchors.

Axis rules:

- setuptools: the newest PyPI release inside the range setup.py
  declares (the ``<82`` cap is parsed from install_requires). Only the
  per-version sweep matrices are bumped; the singleton pins of the
  python/mac/uv jobs carry their own semantics ("newest every Python
  supports", "the devenv pin") and are left alone.
- pip: the newest PyPI release (the pip matrix lives in run-tests.yml
  only: the uv pipeline never spawns pip).
- uv: the matrix is the setup.py floor plus the five most recent
  stable releases; the window slides as new releases land (the uv
  matrix lives in test-uv.yml only).
- python: the newest stable minor per endoflife.date, added only after
  a devenv probe proves the version builds; also seeds the matching
  .github/workflows/scripts-X.Y.cfg from the previous minor.

Edits are line- and tuple-level text surgery, never yaml load/dump:
the workflow files' comments and house style survive. Every matcher
must hit exactly once per expected file, or the script fails loudly
instead of guessing. When uvx is on PATH, the drift harness runs as
the final gate; a red harness means a non-zero exit.
"""

from __future__ import annotations

import importlib.util
import json
import re
import shutil
import subprocess
import sys
import urllib.request
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
WORKFLOWS = (REPO / ".github" / "workflows" / "run-tests.yml",
             REPO / ".github" / "workflows" / "test-uv.yml")
JOBS_PY = REPO / "dagger" / "src" / "buildout_ci" / "jobs.py"
TEST_JOBS_PY = REPO / "dagger" / "tests" / "test_jobs.py"
SETUP_PY = REPO / "setup.py"


def version_key(version: str) -> tuple[int, ...]:
    return tuple(int(part) for part in version.split("."))


def fetch_json(url: str):
    with urllib.request.urlopen(url, timeout=30) as response:
        return json.load(response)


def pypi_releases(package: str) -> list[str]:
    """All pure-numeric releases of ``package``, oldest first."""
    data = fetch_json(f"https://pypi.org/pypi/{package}/json")
    releases = [v for v in data["releases"]
                if re.fullmatch(r"\d+(\.\d+)+", v)]
    return sorted(releases, key=version_key)


def declared_range(requirement: str) -> tuple[str, str | None]:
    """The >= lower and < upper bounds of a setup.py requirement."""
    text = SETUP_PY.read_text()
    match = re.search(rf"'{requirement}>=([\d.]+?)(?:,<([\d.]+))?\s*'", text)
    if not match:
        sys.exit(f"setup.py: cannot parse the declared {requirement} range")
    return match.group(1), match.group(2)


def render_flow(values: list[str]) -> str:
    return "[" + ", ".join(f'"{v}"' for v in values) + "]"


class WorkflowFile:
    """Line-level access to one workflow file's matrix lists."""

    def __init__(self, path: Path):
        self.path = path
        self.lines = path.read_text().splitlines(keepends=True)
        self.dirty = False

    def get_list(self, index: int) -> tuple[str, str, list[str]]:
        """The (indent, key, values) of a flow-list line."""
        match = re.match(r"^(\s*)([\w-]+): (\[.*\])$",
                         self.lines[index].rstrip("\n"))
        if not match:
            sys.exit(f"{self.path.name} line {index + 1}: "
                     "not a flow-list line")
        indent, key, flow = match.groups()
        values = [v.strip().strip('"') for v in
                  flow.strip("[]").split(",") if v.strip()]
        return indent, key, values

    def matrix_lines(self, key: str) -> list[int]:
        return [i for i, line in enumerate(self.lines)
                if re.match(rf"^\s*{re.escape(key)}: \[.*\]$",
                            line.rstrip("\n"))]

    def job_matrix_lines(self, job: str, key: str) -> list[int]:
        """The flow-list lines for ``key`` in the named job's matrix.

        Job ids are the two-space keys under the top-level ``jobs:``
        mapping. Keying on the job, not the list's contents, is what
        tells the setuptools sweep apart from the pip job's two-entry
        setuptools cross-product.
        """
        current = None
        in_jobs = False
        hits = []
        for i, raw in enumerate(self.lines):
            line = raw.rstrip("\n")
            if line == "jobs:":
                in_jobs = True
                continue
            if not in_jobs:
                continue
            header = re.match(r"^  ([\w-]+):$", line)
            if header:
                current = header.group(1)
            if current == job and re.match(
                    rf"^\s*{re.escape(key)}: \[.*\]$", line):
                hits.append(i)
        return hits

    def set_list(self, index: int, values: list[str]) -> None:
        indent, key, current = self.get_list(index)
        if current != values:
            self.lines[index] = f"{indent}{key}: {render_flow(values)}\n"
            self.dirty = True

    def flush(self) -> None:
        if self.dirty:
            self.path.write_text("".join(self.lines))


class JobsTable:
    """Tuple-level access to the dagger job table's version lists."""

    def __init__(self, path: Path = JOBS_PY):
        self.path = path
        self.text = path.read_text()
        self.dirty = False

    def _replace_tuple(self, anchor: str, values: list[str],
                       count: int = 1) -> None:
        """Rewrite the tuple literals opened right after ``anchor``.

        Anchors are loop headers (`for st in (`, optionally extended
        with first values for uniqueness), never bare version strings:
        a version like "3.10" also appears as a `python=` argument and
        would point the edit at the wrong parenthesized block. Missing
        or ambiguous anchors fail loudly.
        """
        hits = [m.start() for m in re.finditer(re.escape(anchor), self.text)]
        if len(hits) != count:
            sys.exit(f"{self.path.name}: anchor {anchor!r} matched "
                     f"{len(hits)} times, expected {count}")
        for hit in reversed(hits):  # rightmost first: positions hold
            open_paren = self.text.find("(", hit)  # the anchor's own
            # opener; searching from inside the anchor skips it when the
            # anchor already contains it (e.g. `for st in (\n`)
            close_paren = self.text.find(")", open_paren)
            block = self.text[open_paren:close_paren + 1]
            current = re.findall(r'"([^"]+)"', block)
            if current == values:
                continue
            if "\n" in block:  # one value per line, 16-space indent
                body = "".join(f'                "{v}",\n' for v in values)
                new = "(\n" + body + "            )"
            else:
                new = "(" + ", ".join(f'"{v}"' for v in values) + ")"
            self.text = (self.text[:open_paren] + new
                         + self.text[close_paren + 1:])
            self.dirty = True

    def set_setuptools_sweep(self, values: list[str]) -> None:
        # the newline pins the multiline sweep tuples, which the
        # run-tests.yml and test-uv.yml setuptools jobs share; the pip
        # job's `for st in ("65.7.0", "75.8.2")` cross stays single-line
        self._replace_tuple("for st in (\n", values, count=2)

    def set_pip(self, values: list[str]) -> None:
        self._replace_tuple("for pip in (", values)

    def set_python(self, sweep: list[str], scripts: list[str]) -> None:
        # the python family skips 3.10 (covered by the setuptools job)
        # and the scripts family runs every supported python; both lists
        # are mirrored into the uv-installer rows, and the scripts-head
        # variant starts at 3.10 and is out of scope here
        self._replace_tuple('for py in ("3.9", "3.11"', sweep, count=2)
        self._replace_tuple('for py in ("3.9", "3.10"', scripts, count=2)

    def set_uv(self, values: list[str]) -> None:
        self._replace_tuple("for uv in (", values)

    def flush(self) -> None:
        if self.dirty:
            self.path.write_text(self.text)


def bump_setuptools(workflows: list[WorkflowFile], jobs: JobsTable) -> str:
    _, upper = declared_range("setuptools")
    ceiling = int(upper.split(".")[0]) if upper else None
    candidates = [v for v in pypi_releases("setuptools")
                  if ceiling is None or version_key(v)[0] < ceiling]
    newest = candidates[-1]
    union: set[str] = set()
    lines = []
    for wf in workflows:
        sweeps = wf.job_matrix_lines("setuptools", "setuptools-version")
        if len(sweeps) != 1:
            sys.exit(f"{wf.path.name}: expected exactly one "
                     "setuptools-version list in the setuptools job")
        union.update(wf.get_list(sweeps[0])[2])
        lines.append((wf, sweeps[0]))
    sweep = sorted(union | {newest}, key=version_key)
    for wf, index in lines:
        wf.set_list(index, sweep)
    jobs.set_setuptools_sweep(sweep)
    return (f"setuptools: sweep now tops at {sweep[-1]}"
            if sweep[-1] == newest and newest not in union
            else f"setuptools: {sweep[-1]} already current")


def bump_pip(workflow: WorkflowFile, jobs: JobsTable,
             test_jobs: JobsTable) -> str:
    newest = pypi_releases("pip")[-1]
    lines = workflow.job_matrix_lines("pip", "pip-version")
    if len(lines) != 1:
        sys.exit(f"{workflow.path.name}: expected one pip-version list "
                 "in the pip job")
    current = workflow.get_list(lines[0])[2]
    # always write both sides: a rerun after a partial failure must
    # heal the tree, not skip the jobs.py half of the edit
    updated = sorted(set(current) | {newest}, key=version_key)
    workflow.set_list(lines[0], updated)
    jobs.set_pip(updated)
    # test_select_jobs_pip pins the pip tuple literally
    test_jobs._replace_tuple("for pip in (", updated)
    return (f"pip: {newest} already current" if newest in current
            else f"pip: added {newest}")


def bump_uv(workflow: WorkflowFile, jobs: JobsTable) -> str:
    floor, _ = declared_range("uv")
    recent = pypi_releases("uv")[-5:]
    wanted = [floor] + [v for v in recent if v != floor]
    lines = workflow.job_matrix_lines("uv", "uv-version")
    if len(lines) != 1:
        sys.exit(f"{workflow.path.name}: expected one uv-version list "
                 "in the uv job")
    current = workflow.get_list(lines[0])[2]
    workflow.set_list(lines[0], wanted)
    jobs.set_uv(wanted)
    if current == wanted:
        return f"uv: window already current ({', '.join(wanted)})"
    return f"uv: window now {', '.join(wanted)}"


def latest_python_minor() -> str:
    cycles = fetch_json("https://endoflife.date/api/python.json")
    for cycle in cycles:  # newest cycle first
        latest = str(cycle.get("latest", ""))
        if re.fullmatch(r"\d+\.\d+\.\d+", latest):
            return str(cycle["cycle"])
    sys.exit("endoflife.date: no stable python cycle found")


def devenv_supports(minor: str) -> bool:
    if not shutil.which("devenv"):
        print(f"python: devenv not on PATH, cannot probe {minor}; "
              "skipping")
        return False
    print(f"python: probing devenv support for {minor} "
          "(may take a minute on a cold cache)")
    probe = subprocess.run(
        ["devenv", "shell",
         "--option", f"languages.python.version:string:{minor}",
         "--", "python", "--version"],
        cwd=REPO, capture_output=True, text=True, timeout=900,
        check=False)
    return probe.returncode == 0


def bump_python(workflows: list[WorkflowFile], jobs: JobsTable) -> str:
    newest = latest_python_minor()
    sweeps: set[str] = set()
    scripts: set[str] = set()
    per_file = []
    for wf in workflows:
        sweep_i = wf.job_matrix_lines("python", "python-version")
        scripts_i = wf.job_matrix_lines("generate-scripts", "python-version")
        if len(sweep_i) != 1 or len(scripts_i) != 1:
            sys.exit(f"{wf.path.name}: expected one python-version list "
                     "in each of the python and generate-scripts jobs")
        sweeps.update(wf.get_list(sweep_i[0])[2])
        scripts.update(wf.get_list(scripts_i[0])[2])
        per_file.append((wf, sweep_i[0], scripts_i[0]))
    added = newest not in sweeps
    if added:
        if not devenv_supports(newest):
            return f"python: {newest} not supported by the devenv yet; skipped"
        sweeps.add(newest)
        scripts.add(newest)
    new_sweep = sorted(sweeps, key=version_key)
    new_scripts = sorted(scripts, key=version_key)
    # the writes are idempotent, so a rerun after a partial failure
    # heals the tree instead of skipping the jobs.py half of the edit
    for wf, sweep_i, scripts_i in per_file:
        wf.set_list(sweep_i, new_sweep)
        wf.set_list(scripts_i, new_scripts)
    jobs.set_python(new_sweep, new_scripts)
    if not added:
        return f"python: {newest} already current"
    previous = new_sweep[-2]
    template = REPO / ".github" / "workflows" / f"scripts-{previous}.cfg"
    (REPO / ".github" / "workflows" / f"scripts-{newest}.cfg").write_text(
        template.read_text())
    return f"python: added {newest} (plus scripts-{newest}.cfg)"


def update_drift_counts() -> None:
    """Rewrite the three count assertions from the edited job table."""
    # Load jobs.py straight from its file, like the drift harness does:
    # importing the buildout_ci package would execute its SDK-generated
    # __init__.py, which imports dagger
    spec = importlib.util.spec_from_file_location("buildout_ci_jobs",
                                                  JOBS_PY)
    if spec is None or spec.loader is None:
        sys.exit(f"cannot load {JOBS_PY}")
    jobs_module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(jobs_module)
    total = len(jobs_module.JOBS)
    families = Counter(job.family for job in jobs_module.JOBS)
    head = sum(1 for job in jobs_module.JOBS
               if job.name.startswith("scripts-head-"))
    cells = total - head - 1  # scripts-head rows and module-tests have
    # no workflow cell; test_workflow_cells_match_job_table enforces it
    text = TEST_JOBS_PY.read_text()
    text, n = re.subn(r"assert len\(cells\) == \d+",
                      f"assert len(cells) == {cells}", text)
    if n != 1:
        sys.exit("test_jobs.py: cells-count assertion not found")
    text, n = re.subn(r"assert len\(jobs\.JOBS\) == \d+",
                      f"assert len(jobs.JOBS) == {total}", text)
    if n != 1:
        sys.exit("test_jobs.py: JOBS-count assertion not found")
    for family, count in sorted(families.items()):
        text, n = re.subn(rf'"{family}": \d+,', f'"{family}": {count},',
                          text)
        if n != 1:
            sys.exit(f"test_jobs.py: family count for {family!r} not found")
    TEST_JOBS_PY.write_text(text)


def main() -> None:
    workflows = [WorkflowFile(path) for path in WORKFLOWS]
    jobs = JobsTable()
    test_jobs = JobsTable(TEST_JOBS_PY)
    print(bump_setuptools(workflows, jobs))
    print(bump_pip(workflows[0], jobs, test_jobs))
    print(bump_uv(workflows[1], jobs))
    print(bump_python(workflows, jobs))
    for wf in workflows:
        wf.flush()
    jobs.flush()
    test_jobs.flush()
    if (any(wf.dirty for wf in workflows) or jobs.dirty
            or test_jobs.dirty):
        update_drift_counts()
        print("test_jobs.py: count assertions regenerated")
    else:
        print("nothing to do: all matrices current")
    if shutil.which("uvx"):
        gate = subprocess.run(
            ["uvx", "--with", "pytest", "--with", "pyyaml",
             "python", "-m", "pytest", "dagger/tests", "-q"],
            cwd=REPO, check=False)
        if gate.returncode != 0:
            sys.exit("drift harness red after the bump; review the diff")
        print("drift harness: green")
    else:
        print("uvx not on PATH; run the drift harness yourself: "
              "uvx --with pytest --with pyyaml python -m pytest "
              "dagger/tests -q")


if __name__ == "__main__":
    main()
