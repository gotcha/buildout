Subprocess tracing support
==========================

``sitecustomize.py`` in this directory auto-installs a MonkeyType
CallTracer in every Python process started with this directory on
``PYTHONPATH`` — including the ``bin/buildout`` subprocesses the
doctests spawn. Traces land in the sqlite DB at ``MT_DB_PATH``.

Used by ``make test-traced``. Env vars:

- ``MT_DB_PATH``: sqlite trace DB (set by the make target)
- ``MONKEYTYPE_TRACE_MODULES``: matched against path *parts*, so use
  ``zc,buildout`` — the dotted ``zc.buildout`` matches nothing.
- ``MT_TRACING_DEBUG``: if set, sitecustomize failures print instead of
  being swallowed.
