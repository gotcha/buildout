The dagger CI retry loop now also treats pip's ``no matching
distributions available for your environment`` conflict report as a
transient index failure. Old pips (21.3.1) report a momentarily hidden
index page with that phrasing inside a ``ResolutionImpossible`` error
instead of ``No matching distribution found``, so the pip-21.3.1 cell
in run 34952880661 failed after 24 s without retrying. A genuine pin
conflict does not print the phrase, so real failures still fail fast.
[gotcha]
