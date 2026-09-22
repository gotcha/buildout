Full resolution hand-off lands for ``installer = uv``: the install loop no
longer resolves one requirement at a time.  Requirements the environment
already satisfies keep their distributions, their installed dependency trees
walk into the working set, and everything still open resolves in a single
``uv pip compile`` (with the buildout's develop projects riding as
overrides), then installs in one batched ``uv pip install``.  Resolution
decisions belong to uv; the loop only consumes installed metadata, and the
per-requirement subprocess fan-out is gone.  The legacy doctest corpus runs
green under both installers.  [gotcha]
