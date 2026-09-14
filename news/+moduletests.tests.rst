The dagger CI module now has its own test harness. The job table moved to
pure-data ``dagger/src/buildout_ci/jobs.py`` and ``dagger/tests/`` checks
it against ``run-tests.yml`` (drift fails the suite), the family
invariants, and the filters. Run it via ``dagger call ci --family
module`` — also a family in the GitHub dagger matrix — or with plain
pytest for the fast loop. [gotcha]
