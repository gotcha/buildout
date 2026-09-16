Offline mode (``buildout -o``) now reuses distributions that were installed
from wheels: their dist-info layout inside the eggs directory was invisible
to the offline environment scan, so offline runs tried (and failed) to
reinstall them.
[gotcha]
