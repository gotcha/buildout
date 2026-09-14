Dagger CI on a dev machine: editing the module or adding a news fragment
no longer busts every job's cache (``dagger/src`` and ``news`` are ignored
in the job source), the per-Python bootstrap prefix (devpi wait, uv
install) is shared and cached across cells, and ``ci`` schedules
longest-family-first. An unchanged repo now reruns a finished cell in
seconds. [gotcha]
