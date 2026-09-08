# tree-sitter-buildout

Tree-sitter grammar for zc.buildout configuration files (`buildout.cfg` and
friends), plus a linter built on top of it.

Status: early skeleton. The grammar parses sections, conditional section
headers, options (`=`, `+=`, `-=`), multiline values with continuations,
`${section:option}` substitutions, `<=` macro options and `=>` dependency
annotations. See `grammar.js` for the exact scope and the deliberate
deviations from `src/zc/buildout/configparser.py` (the hand-rolled reference
parser this mirrors).

## Layout

- `grammar.js` — the grammar definition (the source of truth)
- `src/` — generated parser (`tree-sitter generate`), committed so consumers
  do not need the CLI

## Regenerating

```sh
brew install tree-sitter-cli   # 0.27 used for the initial generation
tree-sitter generate
tree-sitter build -o /tmp/buildout.so
```

## Gotchas discovered while writing this

- **tree-sitter's default `extras` is `[/\s/]`** — whitespace *and newlines*
  are skipped implicitly between tokens. For this line-oriented format that
  silently merged values with their continuation lines. This grammar sets
  `extras: []` explicitly; do not reintroduce a whitespace extra.
- Tokens that can match the empty string (`/[ \t]*/` as a standalone rule
  member) break parsing without a generate-time error — use
  `optional(/[ \t]+/)` instead.
- Rust regex syntax (what tree-sitter compiles to) requires escaping `[`
  inside character classes: `[^\s{}\[\]=:]+`, unlike JS regex literals.
