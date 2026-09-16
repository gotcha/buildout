Fixed spurious ``Uninstalling``/``Installing`` of parts whose recipe
resolves to a develop egg: a packaging run on the develop source tree
(``python -m build``, ``setup.py sdist``) between two buildout runs
regenerated setuptools' sdist manifest ``SOURCES.txt``, which moved the
directory hash behind the recipe signature although the installed dist
was unchanged. ``_dir_hash`` now excludes ``SOURCES.txt``. This also
deflakes the pytest suite under xdist, where the update tests' sdist
builds raced other tests' buildout runs (CI run 35075919620). [gotcha]
