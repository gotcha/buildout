Dagger CI: retry a job command once when its failure output shows a
known-transient fetch signature (``Can't download``, ``No matching
distribution``, connection resets, timeouts) — the failure mode seen
against a cold devpi on GitHub runners. Genuine test failures still fail
fast. [gotcha]
