.PHONY: all test pytest typecheck help
PYTHON_VERSION ?= 3.12
all: test

bin/buildout: setup.py prepare.sh dev.py
	./prepare.sh

bin/test: bin/buildout buildout.cfg
	bin/buildout || bin/buildout.exe

test: bin/test
	PYTHONWARNINGS=ignore bin/test -pvc

test-recipe: bin/test
	PYTHONWARNINGS=ignore bin/test-recipe

test-small: bin/test
	PYTHONWARNINGS=ignore bin/test -pvc -t buildout.txt

typecheck: bin/buildout
	# Static tier of verify-buildout: Astral's ty over the checkout with
	# the repo venv as its Python environment. The _vendor exclude lives
	# in pyproject.toml [tool.ty]. ty comes from the devenv.
	ty check --project . --python venvs/python$(PYTHON_VERSION)/bin/python --output-format concise

pytest: bin/buildout
	# xdist workers are bare-interpreter subprocesses: they do not inherit
	# bin/py's baked sys.path, so pass the eggs via PYTHONPATH.
	PYTHONWARNINGS=ignore PYTHONPATH="$$(ls -d $(PWD)/eggs/v5/*.egg | tr '\n' ':')" \
		bin/py -m pytest src/zc/buildout/tests/pytests/ -v -n auto

help:
	./prepare.sh --help

clean:
	rm -rf venvs .Python .installed.cfg bin build dist lib include parts pip-selfcheck.json develop-eggs src/*.egg-info zc.recipe.egg_/src/*.egg-info
