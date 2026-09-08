;; tree-sitter highlight queries for zc.buildout configuration files.
;; Uses only standard capture groups, so any colorscheme works.

;; Comments — full-line ('#' or ';' in column 0) and trailing after ']'.
(comment) @comment

;; Section headers: [name], [name: condition]
(section_name) @markup.heading

"[" @punctuation.bracket
"]" @punctuation.bracket
"(" @punctuation.bracket
")" @punctuation.bracket

":" @punctuation.delimiter

;; Options: name = value
(option_name) @property

;; '<= base' macro extension: the option name is '<'
((option_name) @keyword.import
  (#eq? @keyword.import "<"))

(assignment) @operator

;; Option values are string-ish; substitutions inside them stand out.
(value) @string
(continuation) @string

;; '$$' escapes a literal dollar.
(escape) @string.escape

;; ${section:option} references (also the ${:option} same-section shorthand).
(substitution) @variable.member

;; '=>' dependency annotations (references to other sections).
(dependency_annotation) @keyword.directive

;; --- conditional section headers -------------------------------------

;; PEP 508 markers (structured by the grammar).
(marker_variable) @variable.builtin
(marker_string) @string
(marker_operator) @operator

;; Boolean operators, in markers and in old-style bodies alike.
"and" @keyword.operator
"or" @keyword.operator
"not" @keyword.operator
"in" @keyword.operator

;; Comparison operators appearing inside old-style (opaque) bodies.
"===" @operator
"==" @operator
"~=" @operator
"!=" @operator
"<=" @operator
">=" @operator
"<" @operator
">" @operator
