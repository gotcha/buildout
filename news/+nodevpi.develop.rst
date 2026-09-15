Dagger CI no longer runs a devpi PyPI proxy container. Measured runs
showed no speed win over the per-Python pip/uv cache volumes plus direct
PyPI access, and the proxy's cold start was the module's main flake
source (GH run 34952880661). The transient-failure retry stays as
PyPI-outage tolerance. Local note: the per-Python pip cache volumes are
URL-keyed to the old devpi index, so the first run after this change
refetches once; the orphaned ``buildout-ci-devpi`` volume lingers until
an engine prune. [gotcha]
