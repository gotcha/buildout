Restore the propagate flags of ``zc.buildout*`` loggers after every pytest:
``Buildout._setup_logging`` and a few ported doctests set
``propagate = False``, and the leak starved later ``caplog`` captures in the
same xdist worker (pytest < 9 attaches its capture handler to the root
logger only — the 3.9 leg runs pytest 8.4.2). [gotcha]
