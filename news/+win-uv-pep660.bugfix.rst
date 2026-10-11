Windows with ``installer = uv``: fix editable (PEP 660) installs of
pyproject-only packages.  Inside a virtualenv, uv's isolated build
environment collapsed to the outer venv identity (an uv-created venv
layered on a stdlib venv re-executes the outer launcher, losing its own
site-packages), so the build backend — e.g. hatchling — was never
importable and the install failed with ``ModuleNotFoundError``.  uv is
now pointed at the real base interpreter on Windows, which keeps the
build environment's identity intact.  [gt-leader]
