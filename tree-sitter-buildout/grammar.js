// Tree-sitter grammar for zc.buildout configuration files.
//
// Mirrors the hand-rolled parser in src/zc/buildout/configparser.py:
//   - comments are full-line only, '#' or ';' in column 0
//   - section headers: [name], [name: expression], optional trailing comment
//   - options: name = value, name += value, name -= value (the +/- may be
//     separated from the name by spaces; the source parser folds it into the
//     key, e.g. "b +")
//   - option names may contain '<' and '>', so '<= base' (macro extension)
//     is an ordinary option whose name is '<'
//   - lines starting with '=>' are rewritten by the source parser to
//     '<part-dependencies> = ...'; we tag them as dependency_annotation
//   - indented lines continue the current option's value; a '#' or ';'
//     in column 0 is a comment even inside a value
//
// Deliberate deviations from configparser.py (kept out of the grammar on
// purpose, to be handled by a linter/host pass instead):
//   - old-style (arbitrary Python) conditional-section expressions are
//     captured as a loose condition_body token stream (structure is
//     linter/host work); PEP 508 marker expressions are parsed structurally
//   - strings with backslash-escaped quotes ('it\'s') inside conditions
//     are rejected; the reference parser's eval would accept them, but
//     packaging's escape-unaware marker strings would not — write the
//     other quote style instead
//   - an empty condition ([a:]) is a syntax error here; the reference
//     regex captures an empty expression and then silently treats the
//     section as unconditional (and [a: ] crashes it with IndexError —
//     here it lints as a WARNING)
//   - whitespace-only lines inside an option value are blank_line nodes,
//     not continuation nodes
//   - blank lines are consumed greedily by the innermost open option;
//     value normalization (strip vs block mode, dedent) is host work

module.exports = grammar({
  name: 'buildout',

  // CRITICAL: override tree-sitter's default extras of [/\s/]. Whitespace
  // and newlines are significant in this line-oriented format (indentation
  // starts a continuation), so nothing may be skipped implicitly.
  extras: $ => [],

  // Whether a comment or blank line after a section's last option belongs
  // to that section or to the file level is genuinely ambiguous; both
  // parses are acceptable, GLR resolves it deterministically.
  conflicts: $ => [
    [$.section],
    [$.option],
    [$.dependency_annotation],
    // The condition token stream is shared by the marker structure and the
    // loose condition_body; GLR keeps both readings and the dynamic
    // precedence on the marker alternative picks the structured parse.
    [$.condition_body, $.marker_group],
    [$.condition_body, $.marker_comparison],
    [$.condition, $.condition_body],
    // every ']' can be a condition_body piece (subscripts) or the closing
    // bracket; only closing at the last possible ']' survives to EOL
    [$.condition_body],
  ],

  rules: {
    source_file: $ => repeat(choice(
      $.section,
      $.comment,
      $._blank_line,
    )),

    section: $ => seq(
      $.section_header,
      repeat(choice(
        $.option,
        $.dependency_annotation,
        $.comment,
        $._blank_line,
      )),
    ),

    section_header: $ => choice(
      // plain: [name]
      seq(
        '[',
        optional(/[ \t]+/),
        $.section_name,
        optional(/[ \t]+/),
        ']',
        optional($._trailing_comment),
        $._newline,
      ),
      // conditional: [name: expression] — the source parser's expression
      // regex ([^#;]*) is greedy and backtracks to the LAST ']' on the line,
      // so expressions may themselves contain ']'. The condition token below
      // mirrors that by maximal munch: it spans ': expr ]' including the
      // closing bracket.
      seq(
        '[',
        optional(/[ \t]+/),
        $.section_name,
        optional(/[ \t]+/),
        $.condition,
        optional($._trailing_comment),
        $._newline,
      ),
    ),

    section_name: $ => /[^\s#\[\]:;{}]+/,

    // ': expression ]' — mirrors the reference parser's two-dialect
    // strategy (configparser.py:181-208: try PEP 508 Marker, fall back to
    // eval). A marker expression is parsed structurally; anything else
    // (old-style arbitrary Python) falls back to a loose condition_body.
    //
    // Tree-sitter's lexer is a global maximal muncher: a single opaque
    // '.*]' token would always out-munch the small marker tokens, so both
    // dialects are lexed from ONE shared token stream (marker tokens plus
    // generic word/punctuation pieces). GLR then keeps both structural
    // interpretations of that stream; the dynamic precedence makes the
    // marker parse win whenever it is valid, exactly like the reference
    // parser tries Marker first.
    //
    // ']' is both legal inside expressions (subscripts, strings) and the
    // terminator ("the last ']' before the optional trailing comment").
    // Every ']' forks the parse (condition_body piece vs. closing bracket);
    // only closing at the LAST possible ']' survives, because after an
    // early close the remaining text is neither a comment nor end-of-line.
    condition: $ => seq(
      ':',
      choice(
        prec.dynamic(1, seq(
          optional($._hws),
          $.marker_expression,
          optional($._hws),
        )),
        $.condition_body,
      ),
      ']',
    ),

    // Old-style (arbitrary Python) expression, kept as a flat sequence of
    // shared tokens. Structure is linter/host work (packaging / ast), just
    // like the reference parser's eval fallback.
    condition_body: $ => repeat1(choice(
      $.marker_string,
      $.marker_variable,
      $._word_run,
      $._punct_run,
      $._catch_all_char,
      $._hws,
      '(', ')', '[', ']',
      'and', 'or', 'not', 'in',
      '===', '==', '~=', '!=', '<=', '>=', '<', '>',
    )),

    // Generic condition-content pieces, shaped so they never out-munch the
    // marker tokens above: words stop before operator/bracket characters,
    // punctuation runs contain no word characters.
    _word_run: $ => /[A-Za-z0-9_.]+/,
    _punct_run: $ => /[-+*\/%=<>!~&|^@$?,.:\\`]+/,
    // any other single character (unicode, ...); loses every tie
    _catch_all_char: $ => token(prec(-2, /[^\s#;\[\]'"]/)),

    // PEP 508 marker expression, following packaging's implementation
    // (packaging._tokenizer / ._parser, packaging>=22), which is what the
    // reference parser and the linter use:
    //   marker      = marker_or
    //   marker_or   = marker_and ('or' marker_and)*
    //   marker_and  = marker_atom ('and' marker_atom)*
    //   marker_atom = '(' marker ')' | marker_var marker_op marker_var
    //   marker_var  = env_var | quoted_string   (either side may be quoted)
    //   marker_op   = ===|==|~=|!=|<=|>=|<|>|in|not in
    // packaging parses 'and'/'or' chains flat and applies and-over-or
    // precedence at evaluation time; we encode the precedence structurally
    // (matches evaluation semantics and yields a useful tree).
    marker_expression: $ => choice(
      $.marker_comparison,
      $.marker_group,
      $.marker_and,
      $.marker_or,
    ),

    marker_or: $ => prec.left(1, seq(
      $.marker_expression, $._hws, 'or', $._hws, $.marker_expression,
    )),

    marker_and: $ => prec.left(2, seq(
      $.marker_expression, $._hws, 'and', $._hws, $.marker_expression,
    )),

    marker_group: $ => seq(
      '(', optional($._hws), $.marker_expression, optional($._hws), ')',
    ),

    marker_comparison: $ => seq(
      choice($.marker_variable, $.marker_string),
      optional($._hws),
      $.marker_operator,
      optional($._hws),
      choice($.marker_variable, $.marker_string),
    ),

    // packaging._tokenizer: QUOTED_STRING = '[^']*' | "[^"]*"
    // (deliberately not escape-aware, like packaging itself; buildout's
    // \x23 / \x3b escapes are plain backslash sequences to this token).
    // Additionally excludes literal '#' / ';', which the buildout framing
    // (configparser.py's [^#;]* expression charset) forbids anywhere in a
    // header line, even inside string literals.
    marker_string: $ => token(choice(/'[^'#\n;]*'/, /"[^"#\n;]*"/)),

    // packaging._tokenizer VARIABLE (wider than PEP 508's env_var list:
    // allows '.', adds python_implementation, extras, dependency_groups).
    // Lexical precedence 1 (tree-sitter's precedence dominates match
    // length): "python_versionology" lexes as marker_variable + a
    // "_word_run" suffix, which is harmless — condition_body unions all
    // shared token types, the marker structure dies on the suffix just
    // like packaging's \b-boundary rejects the name, and the linter reads
    // the raw text either way.
    marker_variable: $ => token(prec(1, choice(
      'python_version',
      'python_full_version',
      /os[._]name/,
      /sys[._]platform/,
      /platform_(release|system)/,
      /platform[._](version|machine|python_implementation)/,
      'python_implementation',
      /implementation_(name|version)/,
      /extras?/,
      'dependency_groups',
    ))),

    marker_operator: $ => choice(
      '===', '==', '~=', '!=', '<=', '>=', '<', '>',
      'in',
      seq('not', $._hws, 'in'),
    ),

    // horizontal whitespace inside condition expressions; conditions are
    // single-line (the reference regex [^#;]* cannot cross a newline)
    _hws: $ => /[ \t]+/,

    // Comments and blank lines do NOT close an open option in the source
    // parser (the comment check `continue`s without touching the current
    // option), so an indented line after them still appends to the value.
    option: $ => seq(
      $.option_name,
      $.assignment,
      optional($.value),
      $._newline,
      repeat(choice($.continuation, $.comment, $._blank_line)),
    ),

    // The source parser folds a trailing '+'/'-' into the key ("b +"),
    // so `a+=1` lexes with the sign inside option_name and `a += 1` with
    // the sign inside assignment. Both shapes are preserved here.
    option_name: $ => /[^\s{}\[\]=:]+/,

    assignment: $ => /[ \t]*[-+]?[ \t]*=[ \t]*/,

    value: $ => repeat1(choice(
      $.substitution,
      $.escape,
      /[^$\n]+/,
      /\$/,
    )),

    substitution: $ => token(seq('${', /[^}\n]*/, '}')),

    // '$$' escapes a literal dollar in the source parser.
    escape: $ => token('$$'),

    // The reference parser accumulates indented continuation lines after
    // '=>' into the <part-dependencies> value, just like option values.
    dependency_annotation: $ => seq(
      token(seq('=>', /[^\n]*/)),
      $._newline,
      repeat(choice($.continuation, $.comment, $._blank_line)),
    ),

    continuation: $ => seq(
      token(/[ \t]+\S[^\n]*/),
      $._newline,
    ),

    comment: $ => token(/[#;][^\n]*/),

    // after ']': either spaced or immediately attached ('[s]; c')
    _trailing_comment: $ => choice(seq(/[ \t]+/, $.comment), $.comment),

    _blank_line: $ => token(/[ \t]*\r?\n/),

    _newline: $ => /\r?\n/,
  },
});
