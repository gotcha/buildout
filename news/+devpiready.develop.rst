Dagger CI: fix a cold-start race where a fresh devpi answered HTTP 200 on
its root page before its package index served, failing the first
``pip install`` of a run (seen once on GitHub Actions). The readiness
probe now requires real index content and the install retries. [gotcha]
