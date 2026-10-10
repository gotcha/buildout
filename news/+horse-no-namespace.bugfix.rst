Importing ``zc.buildout`` no longer crashes with ``AttributeError`` when a
bare-bones ``pkg_resources`` shim lacking ``PkgResourcesDeprecationWarning``
-- for example horse-with-no-namespace under setuptools >= 82 -- was imported
first.  The init-time warnings-filter install now skips the category filter
when the class is absent; filters for a complete pre-imported copy are
unchanged.  Port of upstream 07a19799 in branch shape.
