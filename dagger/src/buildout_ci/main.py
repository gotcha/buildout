"""Run the repo's .github/workflows CI jobs locally under Dagger with a devpi PyPI cache."""

import asyncio
from dataclasses import dataclass
from typing import Annotated

import dagger
from dagger import dag, function, object_type
from dagger.mod import DefaultPath, Ignore

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
            "**/*.egg-info",
            "**/__pycache__",
            ".coverage",
            ".coverage.*",
        ]
    ),
]


@dataclass(frozen=True)
class Job:
    name: str
    python: str
    commands: tuple[tuple[str, ...], ...]
    family: str
    setuptools: str = "75.8.2"
    pip: str = ""
    package: str = ""
    pip_install: tuple[str, ...] = ()


FAMILIES = ("setuptools", "python", "pip", "scripts", "static", "coverage")


def _scripts_commands(makefile: str) -> tuple[tuple[str, ...], ...]:
    return (
        ("make", "-f", makefile, "sandbox/bin/buildout"),
        ("sh", "-c", "sandbox/bin/buildout -v -c .github/workflows/scripts-${PYTHON_VERSION}.cfg annotate buildout"),
        ("sh", "-c", "sandbox/bin/buildout -c .github/workflows/scripts-${PYTHON_VERSION}.cfg"),
        ("sh", "-c", 'test -n "$(ls -A sandbox/eggs)" && test -n "$(ls -A sandbox/downloads/dist)"'),
    )


def _build_jobs() -> tuple[Job, ...]:
    make_and_pytest: tuple[tuple[str, ...], ...] = (("make",), ("make", "pytest"))
    # No Windows job from run-tests.yml: this podman host runs Linux containers only.
    return (
        *(
            Job(
                name=f"setuptools-{st}",
                python="3.10",
                # the workflow skips the pytest step on setuptools 63.0.0
                commands=(("make",),) if st == "63.0.0" else make_and_pytest,
                family="setuptools",
                setuptools=st,
            )
            for st in (
                "63.0.0",
                "65.7.0",
                "69.5.1",
                "74.1.3",
                "75.9.1",
                "79.0.1",
                "80.2.0",
                "80.10.2",
                "81.0.0",
            )
        ),
        Job(
            name="ruff",
            python="3.12",
            commands=(("make", "lint"),),
            family="static",
            # pin to the devenv-provided ruff (devenv.lock nixpkgs rev),
            # so the local gate matches CI exactly
            pip_install=("ruff==0.16.6",),
        ),
        Job(
            name="ty",
            python="3.12",
            commands=(("make", "typecheck"),),
            family="static",
            # pin to the devenv-provided ty: newer ty emits diagnostics
            # inside third-party eggs on the search path
            pip_install=("ty==0.0.78",),
        ),
        Job(
            name="setuptools-61-test-small",
            python="3.10",
            commands=(("make", "test-small"),),
            family="setuptools",
            setuptools="61.0.0",
        ),
        *(
            Job(
                name=f"python-{py}",
                python=py,
                commands=make_and_pytest,
                family="python",
                setuptools="75.6.0",
            )
            for py in ("3.9", "3.11", "3.12", "3.13", "3.14")
        ),
        *(
            Job(
                name=f"pip-{pip}-st-{st}",
                python="3.10",
                commands=make_and_pytest,
                family="pip",
                setuptools=st,
                pip=pip,
            )
            for pip in ("21.3.1", "22.3.1", "23.3.2", "24.3.1", "25.3", "26.1.2")
            for st in ("65.7.0", "75.8.2")
        ),
        # named after the macos workflow job: same make targets, but in a Linux container
        Job(name="mac", python="3.10", commands=make_and_pytest, family="python"),
        Job(name="coverage-legacy", python="3.12", commands=(("make", "coverage"),), family="coverage"),
        Job(name="coverage-pytest", python="3.12", commands=(("make", "coverage-pytest"),), family="coverage"),
        *(
            Job(
                name=f"scripts-{pkg}-py{py}",
                python=py,
                commands=_scripts_commands(".github/workflows/Makefile-scripts"),
                family="scripts",
                package=pkg,
            )
            for py in ("3.9", "3.10", "3.11", "3.12", "3.13", "3.14")
            for pkg in ("zest.releaser", "pyspf")
        ),
        *(
            Job(
                name=f"scripts-head-{pkg}-py{py}",
                python=py,
                commands=_scripts_commands(".github/workflows/Makefile-scripts-setuptools-head"),
                family="scripts",
                package=pkg,
            )
            for py in ("3.10", "3.11", "3.12", "3.13", "3.14")
            for pkg in ("zest.releaser", "pyspf")
        ),
    )


JOBS = _build_jobs()


def _find_job(name: str) -> Job:
    for job in JOBS:
        if job.name == name:
            return job
    valid = "\n".join(job.name for job in JOBS)
    raise ValueError(f"unknown job {name!r}; valid jobs:\n{valid}")


def _check_family(family: str) -> None:
    if not family or family in FAMILIES:
        return
    valid = "\n".join(FAMILIES)
    raise ValueError(f"unknown family {family!r}; valid families:\n{valid}")


def _select_jobs(family: str) -> list[Job]:
    _check_family(family)
    return [job for job in JOBS if not family or job.family == family]


@object_type
class BuildoutCi:
    @function
    def jobs(self, family: str = "") -> str:
        """List the CI job names, one per line, in registry order; pass family to list only that family's."""
        return "\n".join(job.name for job in _select_jobs(family))

    @function
    def families(self) -> str:
        """List the job family names, one per line."""
        return "\n".join(FAMILIES)

    @function
    async def job(self, source: Source, name: str) -> str:
        """Run a single CI job by name (see jobs for valid names)."""
        spec = _find_job(name)
        await self._run(source, self.devpi_service(), spec)
        return f"{name}: ok"

    @function
    async def ci(self, source: Source, concurrency: int = 4, family: str = "") -> str:
        """Run all CI jobs with bounded concurrency against one shared devpi cache.

        Pass family to run only that family's jobs (see families).
        """
        selected = _select_jobs(family)
        semaphore = asyncio.Semaphore(concurrency)
        devpi = self.devpi_service()

        async def run(job: Job) -> str:
            async with semaphore:
                try:
                    await self._run(source, devpi, job)
                except Exception as exc:
                    lines = [ln for ln in str(exc).splitlines() if ln.strip()]
                    return f"FAIL {job.name}: {lines[-1] if lines else exc!r}"
                return f"PASS {job.name}"

        results = await asyncio.gather(*(run(job) for job in selected))
        summary = "\n".join(results)
        if any(result.startswith("FAIL") for result in results):
            raise Exception(summary)
        return summary

    @function
    def devpi_service(self) -> dagger.Service:
        """Return the shared devpi PyPI cache/proxy service (persistent cache volume)."""
        return (
            dag.container()
            .from_("jonasal/devpi-server:6.20.1")
            .with_env_variable("DEVPI_PASSWORD", "password")
            .with_exposed_port(3141)
            .with_mounted_cache("/devpi/server", dag.cache_volume("buildout-ci-devpi"))
            .as_service(
                args="--indexer-backend null --serverdir /devpi/server --request-timeout 60".split(),
                use_entrypoint=True,
            )
        )

    def _base(self, source: dagger.Directory, devpi: dagger.Service, job: Job) -> dagger.Container:
        ctr = (
            dag.container()
            .from_(f"python:{job.python}")
            .with_service_binding("devpi", devpi)
            .with_env_variable("buildout_testing_index_url", "http://devpi:3141/root/pypi/+simple/")
            .with_env_variable("PIP_INDEX_URL", "http://devpi:3141/root/pypi/+simple")
            .with_env_variable("PIP_TRUSTED_HOST", "devpi")
            .with_env_variable("PYTHONWARNINGS", "ignore")
            .with_env_variable("USE_UV", "1")
            .with_env_variable("UV_VENV_CLEAR", "1")
            .with_env_variable("PYTHON_VERSION", job.python)
        )
        if job.setuptools:
            ctr = ctr.with_env_variable("SETUPTOOLS_VERSION", job.setuptools)
        if job.pip:
            ctr = ctr.with_env_variable("PIP_VERSION", job.pip)
        if job.package:
            ctr = ctr.with_env_variable("PACKAGE", job.package)
        return (
            ctr.with_mounted_directory("/src", source)
            .with_workdir("/src")
            .with_exec(["sh", "-c", "until curl -sf http://devpi:3141/ >/dev/null; do sleep 1; done"])
            .with_exec(["pip", "install", "--quiet", "uv", *job.pip_install])
        )

    async def _run(self, source: dagger.Directory, devpi: dagger.Service, job: Job) -> None:
        ctr = self._base(source, devpi, job)
        for command in job.commands:
            ctr = ctr.with_exec(list(command))
        await ctr.stdout()
