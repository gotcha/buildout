.PHONY: all test pytest typecheck test-traced help
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

typecheck: bin/test
	# Static tier of verify-buildout: Astral's ty over the checkout with
	# the repo venv as its Python environment. The _vendor exclude lives
	# in pyproject.toml [tool.ty]. ty comes from the devenv.
	# Depends on bin/test (not bare bin/buildout): the buildout run is what
	# materializes eggs/, and the eggs go on ty's search path below so
	# imports that resolve at test time also resolve statically.
	ty check --project . --python venvs/python$(PYTHON_VERSION)/bin/python --output-format concise $(foreach e,$(wildcard eggs/v5/*.egg),--extra-search-path $e)

pytest: bin/test
	# xdist workers are bare-interpreter subprocesses: they do not inherit
	# bin/py's baked sys.path, so pass the eggs via PYTHONPATH. Let Python
	# itself assemble the value: the PWD variable is empty when make is
	# invoked from PowerShell (Windows CI), and the PYTHONPATH separator
	# is ';' on Windows but ':' elsewhere.
	PYTHONWARNINGS=ignore PYTHONPATH="$$(bin/py -c 'import glob, os; print(os.pathsep.join(glob.glob(os.path.join(os.getcwd(), "eggs", "v5", "*.egg"))))')" \
		bin/py -m pytest src/zc/buildout/tests/pytests/ -v -n auto

help:
	./prepare.sh --help

clean:
	rm -rf venvs .Python .installed.cfg bin build dist lib include parts pip-selfcheck.json develop-eggs src/*.egg-info zc.recipe.egg_/src/*.egg-info

# Temporary slow tier: run the suite with MonkeyType tracing in every
# process, including spawned bin/buildout subprocesses (via
# etc/tracing/sitecustomize.py on PYTHONPATH). Traces land in
# .monkeytype-trace/monkeytype.sqlite3 for monkeytype stub/apply.
test-traced: bin/test
	rm -rf .monkeytype-trace && mkdir -p .monkeytype-trace
	PYTHONPATH=$(CURDIR)/etc/tracing \
	MT_DB_PATH=$(CURDIR)/.monkeytype-trace/monkeytype.sqlite3 \
	MONKEYTYPE_TRACE_MODULES=zc,buildout \
	PYTHONWARNINGS=ignore \
	bin/test -pvc
