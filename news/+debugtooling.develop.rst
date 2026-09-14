Dagger CI debug tooling: ``dagger call debug --name <job>`` returns the
cell's container stopped at its first failing command (chain
``terminal`` for a shell inside the failed cell), cell failures now carry
the failing command and the last 30 output lines instead of one opaque
line, and ``dagger call smoke`` runs a ~half-minute module self-check.
[gotcha]
