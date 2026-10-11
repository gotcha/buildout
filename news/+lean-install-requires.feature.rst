``wheel`` is no longer installed with ``zc.buildout``: nothing imports
it, it survived only as a name the self-upgrade check resolves on
demand.  ``setuptools`` now ships on Windows only
(``sys_platform == "win32"`` marker), where uv-mode script generation
still imports its launcher, and otherwise comes from the
``zc.buildout[pip]`` extra, which keeps its ``pip>=25.0`` floor.
Every POSIX ``setuptools`` import is gated on pip mode or the legacy
source-build path.  ``packaging``, ``platformdirs``, ``uv`` and the
Python<3.11 ``tomli`` marker are unchanged.
[gt-builder]
