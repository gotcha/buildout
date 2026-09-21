"""Tests for etc/bump_ci_versions.py, the CI-matrix version bumper.

All offline: the script's network seams (pypi_releases,
latest_python_minor) and its devenv probe are monkeypatched, and its
module-level path constants point at a throwaway repo tree (tmp_path),
so a test run never touches the real matrices or PyPI.
"""

import importlib.util
import sys
from collections import Counter
from pathlib import Path
from types import SimpleNamespace

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPO_ROOT / "etc" / "bump_ci_versions.py"


def _load_bumper():
    # Load the script straight from its file, like the drift harness
    # loads jobs.py: etc/ is not a package.
    spec = importlib.util.spec_from_file_location(
        "bump_ci_versions", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _exec_module(path):
    spec = importlib.util.spec_from_file_location("fake_module", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


bumper = _load_bumper()

SETUP_PY = """\
from setuptools import setup

setup(
    name="zc.buildout",
    install_requires=[
        'setuptools>=61.0.0,<82',
        'uv>=0.12.11',
    ],
    python_requires='>=3.9',
)
"""

RUN_TESTS_YML = """\
name: tests
on:
  push:

# a house comment that must survive any bump
jobs:
  setuptools:
    strategy:
      matrix:
        os: [ubuntu-24.04]
        python-version: ["3.10"]
        setuptools-version: ["63.0.0", "75.9.1"]
  python:
    strategy:
      matrix:
        os: [ubuntu-24.04]
        python-version: ["3.9", "3.11"]
        setuptools-version: ["75.6.0"]
  pip:
    strategy:
      matrix:
        os: [ubuntu-24.04]
        pip-version: ["21.3.1"]
        setuptools-version: ["65.7.0", "75.8.2"]
  generate-scripts:
    strategy:
      matrix:
        os: [ubuntu-22.04]
        python-version: ["3.9", "3.10", "3.11"]
"""

TEST_UV_YML = """\
name: tests-uv
on:
  push:

jobs:
  setuptools:
    strategy:
      matrix:
        os: [ubuntu-24.04]
        python-version: ["3.10"]
        setuptools-version: ["63.0.0", "75.9.1"]
  python:
    strategy:
      matrix:
        os: [ubuntu-24.04]
        python-version: ["3.9", "3.11"]
        setuptools-version: ["75.6.0"]
  uv:
    strategy:
      matrix:
        os: [ubuntu-24.04]
        python-version: ["3.12"]
        setuptools-version: ["81.0.0"]
        uv-version: ["0.12.11", "0.12.13"]
  generate-scripts:
    strategy:
      matrix:
        os: [ubuntu-22.04]
        python-version: ["3.9", "3.10", "3.11"]
"""

FAKE_JOBS_PY = '''\
"""Fake dagger job table: the anchor shapes the bumper rewrites."""

from collections import namedtuple

Job = namedtuple("Job", "name family")

JOBS = tuple(
    [
        Job(name=f"setuptools-{st}", family="setuptools")
        for st in (
            "63.0.0",
            "75.9.1",
        )
    ]
    + [
        Job(name=f"uv-setuptools-{st}", family="uv")
        for st in (
            "63.0.0",
            "75.9.1",
        )
    ]
    + [
        Job(name=f"python-{py}", family="python")
        for py in ("3.9", "3.11")
    ]
    + [
        Job(name=f"uv-python-{py}", family="uv")
        for py in ("3.9", "3.11")
    ]
    + [
        Job(name=f"pip-{pip}-{st}", family="pip")
        for pip in ("21.3.1",)
        for st in ("65.7.0", "75.8.2")
    ]
    + [
        Job(name=f"uv-{uv}", family="uv")
        for uv in ("0.12.11", "0.12.13")
    ]
    + [
        Job(name=f"scripts-zest.releaser-py{py}", family="scripts")
        for py in ("3.9", "3.10", "3.11")
    ]
    + [
        Job(name=f"scripts-uv-zest.releaser-py{py}", family="uv")
        for py in ("3.9", "3.10", "3.11")
    ]
    + [Job(name="module-tests", family="module")]
)
'''

FAKE_TEST_JOBS_PY = '''\
"""Fake drift-harness assertions: the shapes update_drift_counts rewrites."""

FAMILY_COUNTS = {
    "module": 1,
    "pip": 2,
    "python": 2,
    "scripts": 3,
    "setuptools": 2,
    "uv": 9,
}


def test_select_jobs_pip():
    expected = [
        f"pip-{pip}-st-{st}"
        for pip in ("21.3.1",)
        for st in ("65.7.0", "75.8.2")
    ]
    assert len(expected) == 2


def test_counts(jobs):
    cells = [job for job in jobs.JOBS if job.family != "module"]
    assert len(cells) == 18
    assert len(jobs.JOBS) == 19
'''

SCRIPTS_CFG = "[buildout]\nparts = scripts\n"


@pytest.fixture
def fake_repo(tmp_path, monkeypatch):
    root = tmp_path / "repo"
    workflows = root / ".github" / "workflows"
    workflows.mkdir(parents=True)
    (root / "dagger" / "tests").mkdir(parents=True)
    (root / "dagger" / "src" / "buildout_ci").mkdir(parents=True)
    (root / "setup.py").write_text(SETUP_PY)
    (workflows / "run-tests.yml").write_text(RUN_TESTS_YML)
    (workflows / "test-uv.yml").write_text(TEST_UV_YML)
    (workflows / "scripts-3.11.cfg").write_text(SCRIPTS_CFG)
    jobs_py = root / "dagger" / "src" / "buildout_ci" / "jobs.py"
    jobs_py.write_text(FAKE_JOBS_PY)
    test_jobs_py = root / "dagger" / "tests" / "test_jobs.py"
    test_jobs_py.write_text(FAKE_TEST_JOBS_PY)
    upstream = SimpleNamespace(
        releases={
            "setuptools": ["61.0.0", "63.0.0", "75.9.1", "81.0.0", "82.0.0"],
            "pip": ["21.3.1", "26.2.1"],
            "uv": ["0.12.9", "0.12.11", "0.12.13", "0.12.14",
                   "0.12.15", "0.12.16", "0.12.17", "0.12.18"],
        },
        newest_python="3.12",
        devenv_ok=True,
    )
    monkeypatch.setattr(bumper, "REPO", root)
    monkeypatch.setattr(bumper, "WORKFLOWS", (
        workflows / "run-tests.yml", workflows / "test-uv.yml"))
    monkeypatch.setattr(bumper, "JOBS_PY", jobs_py)
    monkeypatch.setattr(bumper, "TEST_JOBS_PY", test_jobs_py)
    monkeypatch.setattr(bumper, "SETUP_PY", root / "setup.py")
    monkeypatch.setattr(
        bumper, "pypi_releases", lambda package: upstream.releases[package])
    monkeypatch.setattr(
        bumper, "latest_python_minor", lambda: upstream.newest_python)
    monkeypatch.setattr(
        bumper, "devenv_supports", lambda minor: upstream.devenv_ok)
    # no uvx by default: main() takes its documented skip path
    monkeypatch.setattr(
        bumper, "shutil", SimpleNamespace(which=lambda name: None))
    return SimpleNamespace(
        root=root, workflows=workflows, jobs_py=jobs_py,
        test_jobs_py=test_jobs_py, upstream=upstream)


def _workflows(fake_repo):
    return [bumper.WorkflowFile(fake_repo.workflows / name)
            for name in ("run-tests.yml", "test-uv.yml")]


def _snapshot(root):
    return {path: path.read_bytes()
            for path in sorted(root.rglob("*"))
            if path.is_file() and "__pycache__" not in path.parts}


def test_version_key_orders_numerically():
    sorted_uv = sorted(["0.12.10", "0.12.9"], key=bumper.version_key)
    assert sorted_uv == ["0.12.9", "0.12.10"]


def test_pypi_releases_filters_prereleases_and_sorts(monkeypatch):
    monkeypatch.setattr(bumper, "fetch_json", lambda url: {
        "releases": {v: [] for v in
                     ("0.12.10", "0.12.2", "0.12.11rc1", "0.12", "rc1")}})
    assert bumper.pypi_releases("uv") == ["0.12", "0.12.2", "0.12.10"]


def test_latest_python_minor_skips_prerelease_cycles(monkeypatch):
    monkeypatch.setattr(bumper, "fetch_json", lambda url: [
        {"cycle": "3.15", "latest": "3.15.0a2"},
        {"cycle": "3.14", "latest": "3.14.0"},
    ])
    assert bumper.latest_python_minor() == "3.14"


def test_devenv_supports_requires_binary_and_green_probe(monkeypatch):
    calls = []

    def fake_run(args, **kwargs):
        calls.append(args)
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(bumper, "shutil",
                        SimpleNamespace(which=lambda name: None))
    assert not bumper.devenv_supports("3.15")
    assert calls == []  # no probe without the devenv binary
    monkeypatch.setattr(bumper, "shutil",
                        SimpleNamespace(which=lambda name: "/nix/devenv"))
    monkeypatch.setattr(bumper, "subprocess", SimpleNamespace(run=fake_run))
    assert bumper.devenv_supports("3.15")
    assert "languages.python.version:string:3.15" in calls[0]

    def red_run(*args, **kwargs):
        return SimpleNamespace(returncode=1)

    monkeypatch.setattr(bumper, "subprocess", SimpleNamespace(run=red_run))
    assert not bumper.devenv_supports("3.15")


def test_declared_range_reads_floor_and_cap(fake_repo):
    assert bumper.declared_range("setuptools") == ("61.0.0", "82")
    assert bumper.declared_range("uv") == ("0.12.11", None)


def test_declared_range_missing_requirement_exits(fake_repo):
    with pytest.raises(SystemExit):
        bumper.declared_range("pip")


def test_job_matrix_lines_scope_to_the_named_job(fake_repo):
    wf = bumper.WorkflowFile(fake_repo.workflows / "run-tests.yml")
    sweep = wf.job_matrix_lines("setuptools", "setuptools-version")
    cross = wf.job_matrix_lines("pip", "setuptools-version")
    assert len(sweep) == 1
    assert len(cross) == 1
    assert wf.get_list(sweep[0])[2] == ["63.0.0", "75.9.1"]
    # the pip job's setuptools cross-product is not the sweep
    assert wf.get_list(cross[0])[2] == ["65.7.0", "75.8.2"]


def test_set_list_rewrites_only_the_flow_line(fake_repo):
    path = fake_repo.workflows / "run-tests.yml"
    before = path.read_text()
    wf = bumper.WorkflowFile(path)
    index = wf.job_matrix_lines("setuptools", "setuptools-version")[0]
    wf.set_list(index, ["63.0.0", "75.9.1"])
    assert not wf.dirty  # same values: no rewrite
    wf.set_list(index, ["63.0.0", "75.9.1", "81.0.0"])
    assert wf.dirty
    wf.flush()
    after = path.read_text()
    assert 'setuptools-version: ["63.0.0", "75.9.1", "81.0.0"]' in after
    assert "# a house comment that must survive any bump" in after
    assert len(after.splitlines()) == len(before.splitlines())


def test_get_list_rejects_a_non_flow_line(fake_repo):
    wf = bumper.WorkflowFile(fake_repo.workflows / "run-tests.yml")
    with pytest.raises(SystemExit):
        wf.get_list(0)  # "name: tests"


def test_replace_tuple_rewrites_multiline_and_singleline(fake_repo):
    table = bumper.JobsTable(fake_repo.jobs_py)
    table.set_setuptools_sweep(["63.0.0", "75.9.1", "81.0.0"])
    table.set_pip(["21.3.1", "26.2.1"])
    table.flush()
    text = fake_repo.jobs_py.read_text()
    assert text.count(
        'for st in (\n'
        '                "63.0.0",\n'
        '                "75.9.1",\n'
        '                "81.0.0",\n'
        '            )') == 2
    # the pip job's setuptools cross stays single-line and untouched
    assert 'for st in ("65.7.0", "75.8.2")' in text
    assert 'for pip in ("21.3.1", "26.2.1")' in text
    module = _exec_module(fake_repo.jobs_py)
    assert sum(1 for job in module.JOBS if job.family == "setuptools") == 3


def test_replace_tuple_missing_or_ambiguous_anchor_exits(fake_repo):
    table = bumper.JobsTable(fake_repo.jobs_py)
    with pytest.raises(SystemExit):
        table._replace_tuple("for nog in (", ["1.0"])
    with pytest.raises(SystemExit):
        # the setuptools sweep tuple exists twice: count=1 must refuse
        table._replace_tuple("for st in (\n", ["63.0.0"])


def test_bump_setuptools_adds_newest_below_cap(fake_repo):
    workflows = _workflows(fake_repo)
    jobs = bumper.JobsTable(fake_repo.jobs_py)
    message = bumper.bump_setuptools(workflows, jobs)
    assert message == "setuptools: sweep now tops at 81.0.0"
    for wf in workflows:
        index = wf.job_matrix_lines("setuptools", "setuptools-version")[0]
        assert wf.get_list(index)[2] == ["63.0.0", "75.9.1", "81.0.0"]
    # 82.0.0 sits above the setup.py cap: not a candidate
    assert jobs.text.count('"81.0.0"') == 2
    assert "82.0.0" not in jobs.text


def test_bump_setuptools_noop_when_current(fake_repo):
    fake_repo.upstream.releases["setuptools"] = ["63.0.0", "75.9.1"]
    workflows = _workflows(fake_repo)
    jobs = bumper.JobsTable(fake_repo.jobs_py)
    message = bumper.bump_setuptools(workflows, jobs)
    assert message == "setuptools: 75.9.1 already current"
    assert not any(wf.dirty for wf in workflows)
    assert not jobs.dirty


def test_bump_pip_heals_jobs_table_after_partial_failure(fake_repo):
    path = fake_repo.workflows / "run-tests.yml"
    path.write_text(path.read_text().replace(
        'pip-version: ["21.3.1"]', 'pip-version: ["21.3.1", "26.2.1"]'))
    wf = bumper.WorkflowFile(path)
    jobs = bumper.JobsTable(fake_repo.jobs_py)
    test_jobs = bumper.JobsTable(fake_repo.test_jobs_py)
    # the workflow half of a previous bump landed, the jobs.py half did
    # not: a rerun must still write both sides
    message = bumper.bump_pip(wf, jobs, test_jobs)
    assert message == "pip: 26.2.1 already current"
    assert not wf.dirty
    assert 'for pip in ("21.3.1", "26.2.1")' in jobs.text
    assert 'for pip in ("21.3.1", "26.2.1")' in test_jobs.text


def test_bump_uv_window_is_floor_plus_five_recent(fake_repo):
    wf = bumper.WorkflowFile(fake_repo.workflows / "test-uv.yml")
    jobs = bumper.JobsTable(fake_repo.jobs_py)
    message = bumper.bump_uv(wf, jobs)
    wanted = ["0.12.11", "0.12.14", "0.12.15", "0.12.16", "0.12.17", "0.12.18"]
    assert message == f"uv: window now {', '.join(wanted)}"
    index = wf.job_matrix_lines("uv", "uv-version")[0]
    assert wf.get_list(index)[2] == wanted
    assert 'for uv in ({})'.format(
        ", ".join(f'"{v}"' for v in wanted)) in jobs.text


def test_bump_uv_floor_not_duplicated_when_among_recent(fake_repo):
    fake_repo.upstream.releases["uv"] = [
        "0.12.11", "0.12.12", "0.12.13", "0.12.14", "0.12.15"]
    wf = bumper.WorkflowFile(fake_repo.workflows / "test-uv.yml")
    jobs = bumper.JobsTable(fake_repo.jobs_py)
    bumper.bump_uv(wf, jobs)
    index = wf.job_matrix_lines("uv", "uv-version")[0]
    assert wf.get_list(index)[2] == [
        "0.12.11", "0.12.12", "0.12.13", "0.12.14", "0.12.15"]


def test_bump_python_adds_minor_and_seeds_scripts_cfg(fake_repo):
    workflows = _workflows(fake_repo)
    jobs = bumper.JobsTable(fake_repo.jobs_py)
    message = bumper.bump_python(workflows, jobs)
    assert message == "python: added 3.12 (plus scripts-3.12.cfg)"
    for wf in workflows:
        sweep_i = wf.job_matrix_lines("python", "python-version")[0]
        scripts_i = wf.job_matrix_lines("generate-scripts", "python-version")[0]
        assert wf.get_list(sweep_i)[2] == ["3.9", "3.11", "3.12"]
        assert wf.get_list(scripts_i)[2] == ["3.9", "3.10", "3.11", "3.12"]
    seeded = fake_repo.workflows / "scripts-3.12.cfg"
    assert seeded.read_text() == SCRIPTS_CFG


def test_bump_python_skips_when_devenv_lacks_support(fake_repo):
    fake_repo.upstream.devenv_ok = False
    workflows = _workflows(fake_repo)
    jobs = bumper.JobsTable(fake_repo.jobs_py)
    message = bumper.bump_python(workflows, jobs)
    assert message == "python: 3.12 not supported by the devenv yet; skipped"
    assert not any(wf.dirty for wf in workflows)
    assert not jobs.dirty
    assert not (fake_repo.workflows / "scripts-3.12.cfg").exists()


def test_update_drift_counts_regenerates_from_the_job_table(fake_repo):
    jobs = bumper.JobsTable(fake_repo.jobs_py)
    jobs.set_pip(["21.3.1", "26.2.1"])  # the pip family grows by 2 rows
    jobs.flush()
    bumper.update_drift_counts()
    text = fake_repo.test_jobs_py.read_text()
    assert "assert len(cells) == 20" in text
    assert "assert len(jobs.JOBS) == 21" in text
    assert '"pip": 4,' in text


def test_main_end_to_end_and_rerun_is_a_noop(fake_repo, capsys):
    bumper.main()
    out = capsys.readouterr().out
    assert "setuptools: sweep now tops at 81.0.0" in out
    assert "pip: added 26.2.1" in out
    assert ("uv: window now 0.12.11, 0.12.14, 0.12.15, 0.12.16, "
            "0.12.17, 0.12.18") in out
    assert "python: added 3.12 (plus scripts-3.12.cfg)" in out
    assert "test_jobs.py: count assertions regenerated" in out
    assert "uvx not on PATH" in out

    run_tests = (fake_repo.workflows / "run-tests.yml").read_text()
    test_uv = (fake_repo.workflows / "test-uv.yml").read_text()
    assert 'setuptools-version: ["63.0.0", "75.9.1", "81.0.0"]' in run_tests
    assert 'pip-version: ["21.3.1", "26.2.1"]' in run_tests
    assert 'python-version: ["3.9", "3.11", "3.12"]' in run_tests
    assert 'python-version: ["3.9", "3.10", "3.11", "3.12"]' in run_tests
    assert "# a house comment that must survive any bump" in run_tests
    # singletons and cross-products outside the sweeps stay untouched
    assert 'setuptools-version: ["75.6.0"]' in run_tests
    assert 'setuptools-version: ["65.7.0", "75.8.2"]' in run_tests
    assert 'setuptools-version: ["81.0.0"]' in test_uv
    assert ('uv-version: ["0.12.11", "0.12.14", "0.12.15", '
            '"0.12.16", "0.12.17", "0.12.18"]') in test_uv

    module = _exec_module(fake_repo.jobs_py)
    families = Counter(job.family for job in module.JOBS)
    test_jobs_text = fake_repo.test_jobs_py.read_text()
    assert f"assert len(jobs.JOBS) == {len(module.JOBS)}" in test_jobs_text
    for family, count in sorted(families.items()):
        assert f'"{family}": {count},' in test_jobs_text
    cells = [job for job in module.JOBS
             if not job.name.startswith("scripts-head-")
             and job.name != "module-tests"]
    assert f"assert len(cells) == {len(cells)}" in test_jobs_text
    seeded = fake_repo.workflows / "scripts-3.12.cfg"
    assert seeded.read_text() == SCRIPTS_CFG

    snapshot = _snapshot(fake_repo.root)
    bumper.main()
    out = capsys.readouterr().out
    assert "nothing to do: all matrices current" in out
    assert _snapshot(fake_repo.root) == snapshot


def test_main_runs_the_drift_harness_as_final_gate(fake_repo, monkeypatch,
                                                   capsys):
    runs = []

    def fake_run(args, **kwargs):
        runs.append((args, kwargs))
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(bumper, "shutil",
                        SimpleNamespace(which=lambda name: "/usr/bin/uvx"))
    monkeypatch.setattr(bumper, "subprocess", SimpleNamespace(run=fake_run))
    bumper.main()
    assert runs[0][0][0] == "uvx"
    assert "dagger/tests" in runs[0][0]
    assert runs[0][1]["cwd"] == fake_repo.root
    assert "drift harness: green" in capsys.readouterr().out


def test_main_exits_nonzero_when_the_gate_is_red(fake_repo, monkeypatch):
    def red_run(*args, **kwargs):
        return SimpleNamespace(returncode=1)

    monkeypatch.setattr(bumper, "shutil",
                        SimpleNamespace(which=lambda name: "/usr/bin/uvx"))
    monkeypatch.setattr(bumper, "subprocess", SimpleNamespace(run=red_run))
    with pytest.raises(SystemExit):
        bumper.main()
