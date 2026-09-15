The dagger CI module gives each job command three attempts when the
failure matches a known transient fetch or index signature (``Can't
download``, both ``No matching distribution(s)`` wordings, connection
resets, timeouts) — the failure mode of index flakiness on GitHub
runners, where run 34876803047 showed one cell burning both attempts of
the earlier single-retry scheme on two different transient fetches.
Genuine test failures still fail fast. [gotcha]
