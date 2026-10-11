Require ``setuptools >= 75.8.2``, up from ``61.0.0``.
That release fixed ``pkg_resources.WorkingSet.find`` to consider several
spellings of a requirement name, which is what most of buildout's
remaining ``setuptools`` compatibility code worked around.

Require ``pip >= 25.0`` in the legacy ``zc.buildout[pip]`` extra.
See `issue 755 <https://github.com/buildout/buildout/issues/755>`_.

CI matrices follow the floors: cells below ``setuptools 75.8.2`` cannot
satisfy buildout's own upgrade check (they only appeared to run on
networked runners and failed outright in hermetic containers), so the
lowest tested setuptools is now ``75.9.1``.
