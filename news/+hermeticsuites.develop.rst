The test suites no longer need a network package index. ``prepare.sh``
seeds ``downloads/test-seed/`` with the exact setuptools and wheel
wheels it installed, and the test setups (``buildoutSetUp``, the doc
suites) point every spawned pip at them via ``PIP_NO_INDEX`` +
``PIP_FIND_LINKS``: build isolation on sdist and editable installs and
``python -m build`` then resolve offline. Suite runs now survive a dead
or absent index, and the classic CI matrix legs no longer depend on
PyPI mid-run. Without the seed directory the setups leave the ambient
environment untouched (previous behavior). [gotcha]
