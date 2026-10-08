The ``bin/buildout setup`` / ``runsetup`` command's generated script no
longer pre-imports setuptools in uv installer mode (Phase 4 item 2 of
the uv dependency removal plan): a uv install carries no setuptools
runtime dependency to pre-import.  Pip/legacy mode is unchanged.  A
setup.py that needs setuptools keeps working by importing it itself;
a distutils-style setup.py that silently leaned on the pre-import
should switch to an explicit setuptools import.  [gt-coleader]
