"""Run the repo's .github/workflows CI jobs locally under Dagger."""

import asyncio
import shlex
from typing import Annotated

from dagger.mod import DefaultPath, Ignore

import dagger
from dagger import dag, function, object_type

from .jobs import FAMILIES, FAMILY_MINUTES, Job, _find_job, _select_jobs


class JobFailures(Exception):
    """One or more CI jobs failed; the message carries the run summary."""

Source = Annotated[
    dagger.Directory,
    DefaultPath("."),
    Ignore(
        [
            ".devenv",
            ".monkeytype-trace",
            ".pytest_cache",
            ".ruff_cache",
            "bin",
            "venvs",
            "eggs",
            "downloads",
            "parts",
            "develop-eggs",
            "dist",
            "build",
            "htmlcov",
            "sandbox",
            "dagger/sdk",
            "dagger/.venv",
            "dagger/src",
            "dagger/tests",
            "news",
            "**/*.egg-info",
            "**/__pycache__",
            ".coverage",
            ".coverage.*",
            # repo-local uv pins (Makefile test-uv UV_VERSION): a pin
            # built for the host platform must never shadow the
            # container's own install
            ".uv-pin",
        ]
    ),
]

# The module's own source tree, for the module-family cells that test
# this module: Source above ignores dagger/src, so those cells graft
# this directory in separately (see _run).
ModuleSource = Annotated[
    dagger.Directory,
    DefaultPath("dagger"),
    Ignore(["sdk", ".venv", "__pycache__"]),
]


# Failure output signatures that mean "transient fetch/index failure,
# safe to retry" — observed on GitHub runners.
TRANSIENT_SIGNATURES = (
    "Can't download http",
    "No matching distribution found",
    # Old pips report a momentarily hidden index page as a
    # ResolutionImpossible carrying this qualifier instead (GH run
    # 34952880661, pip-21.3.1 cell). A genuine pin conflict does not
    # print it, so real failures still fail fast.
    "no matching distributions available for your environment",
    "Connection reset",
    "Connection refused",
    "Read timed out",
)

# Fast cells chosen to prove the module machinery end to end (base
# image, module graft, exec layers), not repo coverage.
SMOKE_JOBS = ("ruff", "ty", "radon", "module-tests", "scripts-zest.releaser-py3.12")


def _exec_output(exc: dagger.ExecError) -> str:
    # the failed exec's combined stdout+stderr; each attribute may be
    # empty or raise when the engine has nothing, so guard defensively
    parts = []
    for attr in ("stdout", "stderr"):
        try:
            text = getattr(exc, attr, "") or ""
        except Exception:  # noqa: BLE001 - a failed attribute read must
            # not break summary rendering
            text = ""
        if text.strip():
            parts.append(text.rstrip())
    return "\n".join(parts)


def _failure(job: Job, command: tuple[str, ...], exc: dagger.ExecError) -> RuntimeError:
    # str(exc) is only "exit code: N", so attach the job, the command,
    # and the output tail: the FAIL lines in ci() surface that tail and
    # nobody has to mine engine logs for what actually failed
    tail = "\n".join(_exec_output(exc).splitlines()[-30:])
    return RuntimeError(f"{job.name}: `{shlex.join(command)}` failed with {exc}\nlast output lines:\n{tail}")


@object_type
class BuildoutCi:
    @function
    def jobs(self, family: str = "") -> str:
        """List the CI job names, one per line, in registry order; pass family to list only that family's."""
        return "\n".join(job.name for job in _select_jobs(family))

    @function
    def families(self) -> str:
        """List the repo's job family names, one per line.

        These are the six families the workflow jobs map to. The
        harness-only module family (the module-tests job) is a valid
        family value but intentionally not listed here.
        """
        return "\n".join(FAMILIES)

    @function
    async def job(self, source: Source, module_source: ModuleSource, name: str) -> str:
        """Run a single CI job by name (see jobs for valid names)."""
        spec = _find_job(name)
        await self._run(source, spec, module_source)
        return f"{name}: ok"

    @function
    async def ci(self, source: Source, module_source: ModuleSource, concurrency: int = 4, family: str = "") -> str:
        """Run all CI jobs with bounded concurrency.

        Pass family to run only that family's jobs (see families).
        """
        selected = _select_jobs(family)
        # longest first, so slow cells claim semaphore slots early and the tail
        # stays short; the module family has no duration hint (it is fast), so
        # it sorts last
        selected.sort(key=lambda job: FAMILY_MINUTES.get(job.family, 0), reverse=True)
        semaphore = asyncio.Semaphore(concurrency)

        async def run(job: Job) -> str:
            async with semaphore:
                try:
                    await self._run(source, job, module_source)
                except Exception as exc:  # noqa: BLE001 - CI aggregation:
                    # every job failure becomes a FAIL summary line
                    lines = [ln for ln in str(exc).splitlines() if ln.strip()]
                    return f"FAIL {job.name}: {lines[-1] if lines else exc!r}"
                return f"PASS {job.name}"

        results = await asyncio.gather(*(run(job) for job in selected))
        summary = "\n".join(results)
        if any(result.startswith("FAIL") for result in results):
            raise JobFailures(summary)
        return summary

    @function
    async def debug(self, source: Source, module_source: ModuleSource, name: str) -> dagger.Container:
        """Build the named job's container, stopping at its first failing command, and return it in that state.

        Use `dagger call debug --name <job> terminal` for an interactive
        shell inside the failed cell, or chain further with-exec calls.
        If all commands succeed, returns the final container (useful for
        exploring a green cell).
        """
        spec = _find_job(name)
        ctr = self._base(source, spec)
        if spec.family == "module":
            # mirror _run: graft the dagger/ dir in from module_source
            ctr = ctr.with_directory("/src/dagger", module_source)
        for command in spec.commands:
            # ReturnType.ANY is correct here: this is an inspection flow
            # and the failure state is exactly what we want to keep. It
            # must NOT be used for the retry path in _run — ANY caches
            # nonzero-exit results as layers, so a retry would never
            # re-run the exec.
            probe = ctr.with_exec(list(command), expect=dagger.ReturnType.ANY)
            if await probe.exit_code() != 0:
                return probe
            ctr = probe
        return ctr

    @function
    async def smoke(self, source: Source, module_source: ModuleSource) -> str:
        """Quick module self-check (~2 min warm): the static tier, the module harness, and one scripts cell."""
        results = []
        for name in SMOKE_JOBS:
            try:
                await self._run(source, _find_job(name), module_source)
            except Exception as exc:  # noqa: BLE001 - CI aggregation:
                # every job failure becomes a FAIL summary line
                lines = [ln for ln in str(exc).splitlines() if ln.strip()]
                results.append(f"FAIL {name}: {lines[-1] if lines else exc!r}")
            else:
                results.append(f"PASS {name}")
        summary = "\n".join(results)
        if any(result.startswith("FAIL") for result in results):
            raise JobFailures(summary)
        return summary

    def _base(self, source: dagger.Directory, job: Job) -> dagger.Container:
        ctr = (
            dag.container()
            .from_(f"python:{job.python}")
            .with_env_variable("PYTHONWARNINGS", "ignore")
            .with_env_variable("USE_UV", "1")
            .with_env_variable("UV_VENV_CLEAR", "1")
            .with_env_variable("PYTHON_VERSION", job.python)
            .with_mounted_directory("/src", source)
            .with_workdir("/src")
            # pip and uv caches persist across cells and runs; both tools write
            # caches atomically, so concurrent cells on the same python version
            # can share the volume.
            .with_mounted_cache("/root/.cache/uv", dag.cache_volume(f"buildout-ci-uv-py{job.python}"))
            .with_mounted_cache("/root/.cache/pip", dag.cache_volume(f"buildout-ci-pip-py{job.python}"))
            .with_exec(["pip", "install", "--quiet", "--retries", "10", "uv"])
        )
        # env vars participate in exec cache keys, so everything
        # job-specific stays after the shared prefix
        if job.setuptools:
            ctr = ctr.with_env_variable("SETUPTOOLS_VERSION", job.setuptools)
        if job.pip:
            ctr = ctr.with_env_variable("PIP_VERSION", job.pip)
        if job.package:
            ctr = ctr.with_env_variable("PACKAGE", job.package)
        if job.uv:
            # the Makefile's test-uv target installs this pin with the
            # cell's pip-provided uv and puts it first on PATH
            ctr = ctr.with_env_variable("UV_VERSION", job.uv)
        if job.pip_install:
            ctr = ctr.with_exec(["pip", "install", "--quiet", "--retries", "10", *job.pip_install])
        return ctr

    async def _run(
        self,
        source: dagger.Directory,
        job: Job,
        module_source: dagger.Directory,
    ) -> None:
        ctr = self._base(source, job)
        if job.family == "module":
            # Source ignores dagger/src (module edits must not bust cell
            # caches), but the harness cell needs the module source and
            # its tests: graft the dagger/ dir in from module_source.
            ctr = ctr.with_directory("/src/dagger", module_source)
        for index, command in enumerate(job.commands):
            if job.family == "scripts" and index == 1:
                # mount the sandbox egg caches only after the makefile's
                # `uv venv sandbox` has run: with UV_VENV_CLEAR set, uv
                # clears the target directory, which would empty a cache
                # mounted there before venv creation. uv-installer cells
                # get their own volumes: sharing the pip cells' eggs
                # could mask a uv install that produced nothing.
                installer_suffix = "-uv" if job.installer == "uv" else ""
                ctr = (
                    ctr.with_mounted_cache(
                        "/src/sandbox/eggs",
                        dag.cache_volume(f"buildout-ci-scripts-eggs-py{job.python}-{job.package}{installer_suffix}"),
                    )
                    .with_mounted_cache(
                        "/src/sandbox/downloads",
                        dag.cache_volume(f"buildout-ci-scripts-downloads-py{job.python}-{job.package}{installer_suffix}"),
                    )
                )
                if job.installer == "uv":
                    # scope the installer default to the buildout runs:
                    # the bootstrap exec above stays on pip, exactly like
                    # the workflow's step-level env
                    ctr = ctr.with_env_variable("buildout_testing_installer", "uv")
            ctr = ctr.with_exec(list(command))
            # Transient fetch failures flake in bursts: GH run
            # 34876803047 saw one cell burn both its attempts on two
            # different transient fetches. Give each command three
            # attempts when the failure smells transient.
            attempts = 3
            while True:
                try:
                    await ctr.stdout()
                    break
                except dagger.ExecError as exc:
                    # engine v0.21.9: str(exc) is only "exit code: N"; the
                    # failed command's output lives on .stdout/.stderr
                    attempts -= 1
                    output = f"{exc}\n{_exec_output(exc)}"
                    if attempts == 0 or not any(sig in output for sig in TRANSIENT_SIGNATURES):
                        raise _failure(job, command, exc) from exc
                    # execs are atomic layers: re-awaiting re-runs from the
                    # last good layer; the pip cache volume keeps whatever
                    # the failed attempt fetched. Keep this on the
                    # exception path: ReturnType.ANY caches nonzero-exit
                    # results, so it could never retry.
