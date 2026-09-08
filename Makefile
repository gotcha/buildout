.PHONY: all test pytest help
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

pytest: bin/buildout
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
