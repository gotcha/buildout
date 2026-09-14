Dagger CI: scripts-family cells now cache their sandbox eggs and downloads
in per-Python-and-package volumes, so warm reruns of a scripts cell drop
from ~20 s to ~12-15 s. Mounted only after the sandbox venv exists, so
``UV_VENV_CLEAR`` cannot wipe them. [gotcha]
