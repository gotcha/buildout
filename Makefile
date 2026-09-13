.PHONY: all test pytest coverage coverage-pytest typecheck test-traced lint complexity complexity-baseline help
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

# Coverage variants of both suites. etc/coverage/sitecustomize.py on
# PYTHONPATH starts coverage in the suite process itself and in every
# spawned Python subprocess (bin/buildout drives, pip installs, xdist
# workers) — each interpreter writes its own data file (.coveragerc has
# parallel = true). COVERAGE_PROCESS_START arms the sitecustomize hook.
# An absolute COVERAGE_FILE keeps all data files in the repo root: bin/test
# exits with parts/test as cwd and test-spawned processes chdir around.
# combine/report/html go through bin/coverage: the bare venv python has no
# coverage installed.
COVERAGE_ENV = COVERAGE_PROCESS_START=$(CURDIR)/.coveragerc \
	COVERAGE_FILE=$(CURDIR)/.coverage \
	PYTHONWARNINGS=ignore \
	PYTHONPATH="$(CURDIR)/etc/coverage$$(bin/py -c 'import glob, os; print(os.pathsep + os.pathsep.join(glob.glob(os.path.join(os.getcwd(), "eggs", "v5", "*.egg"))))')"

coverage: bin/test
	rm -f .coverage .coverage.*
	$(COVERAGE_ENV) bin/test -pvc
	bin/coverage combine
	bin/coverage report
	bin/coverage html

coverage-pytest: bin/test
	rm -f .coverage .coverage.*
	$(COVERAGE_ENV) bin/py -m pytest src/zc/buildout/tests/pytests/ -v -n auto
	bin/coverage combine
	bin/coverage report
	bin/coverage html

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

lint:
	# ruff comes from the devenv (devenv.nix); run inside `devenv shell`.
	# Rule selection lives in [tool.ruff] in pyproject.toml — a pragmatic
	# baseline for this legacy tree; tighten it there as code gets cleaned.
	ruff check .

complexity:
	# Cyclomatic-complexity budget gate, a static tier of
	# verify-buildout: no function or method may exceed its entry in
	# etc/complexity-baseline.json, and code without an entry must be
	# radon grade B or better. radon comes from the devenv; the gate
	# script (etc/complexity_gate.py) is stdlib-only. After landing an
	# accepted simplification, refresh and commit the baseline:
	# make complexity-baseline
	python3 etc/complexity_gate.py

complexity-baseline:
	python3 etc/complexity_gate.py --write-baseline

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
