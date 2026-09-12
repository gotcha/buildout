# Auto-start coverage in every Python process that has this directory on
# PYTHONPATH and COVERAGE_PROCESS_START set. Used by the coverage variants
# of the test suites (make coverage / make coverage-pytest): the suites
# spawn bin/buildout and pip subprocesses heavily, and each interpreter
# must start its own tracer — the .coveragerc "parallel = true" setting
# makes every process write its own data file, combined afterwards.
# Never break the host process: no coverage egg importable means the
# process runs untraced.
import os

if os.environ.get("COVERAGE_PROCESS_START"):
    try:
        import coverage
    except ImportError:
        pass
    else:
        coverage.process_startup()
