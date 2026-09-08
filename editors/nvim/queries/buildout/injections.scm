;; Old-style conditional-section expressions are arbitrary Python
;; (the reference parser eval()s them) — highlight them as Python.
;; The grammar keeps the ':' and ']' delimiters outside the
;; condition_body node, so no #offset! trimming is needed.
;;
;; marker_expression is deliberately NOT injected: PEP 508 markers are
;; covered by native captures (see highlights.scm), and marker-only
;; syntax like === would be an error region for a Python grammar.
;; Silently ignored when the python parser is not installed.
((condition_body) @injection.content
  (#set! injection.language "python"))
