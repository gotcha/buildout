# Configure and substitute

Users compose configuration through INI sections, `${section:option}`
substitutions, `extends`, and command-line assignments of the form
`section:option=value` that override file values. `query` and
`annotate` expose what the configuration says and where each value
came from.

These two commands explore the configuration FILES as composed — the
`extends` chain above all, plus assignments and defaults. They do NOT
inspect the result of a run: installed parts, generated scripts, and
`.installed.cfg` are verified on disk (see install-and-inspect),
never through `query`/`annotate`.

## Sub-features

- `assign-override` — a `section:option=value` command-line assignment
  overrides the config file value.
- `annotate-origin` — `annotate` attributes each value to its source
  (which file in the `extends` chain, DEFAULT_VALUE, or
  COMMAND_LINE_VALUE).
- `substitute-raw-vs-cooked` — `${...}` substitution exists in the
  config language; CLI views show raw templates by default and cooked
  values with `--interpolated`; recipes always get cooked values.

## How to get to it (user POV)

- Add sections/options to `buildout.cfg`, then run
  `bin/buildout query section:option` or `bin/buildout annotate`.
- Pass an override inline: `bin/buildout greeting:audience=mars query greeting:audience`.

## Driving it with shell

Preconditions:

- Doctor all-OK; `PYTHONWARNINGS=ignore`; fresh `$D`; `B` set to the
  checkout's `bin/buildout`. All commands in `$D` with:

  ```ini
  [buildout]
  parts =

  [greeting]
  message = hello ${greeting:audience}
  audience = world
  ```

- **Baseline value.** `"$B" query greeting:audience` prints `world`,
  exit 0. Record transcript.
- **Assignment override.** `"$B" greeting:audience=mars query greeting:audience`
  prints `mars` — the assignment won over the file value. Exit 0.
- **Origin attribution.** `"$B" greeting:audience=mars annotate |
  grep -A 3 '\[greeting\]'` shows `audience= mars` with
  `COMMAND_LINE_VALUE` beneath it, while `message` shows
  `buildout.cfg`. Capture into `$ART/assign-override.log`.
- **Substitution template, raw (default).** `"$B" query
  greeting:message` prints the RAW template `hello
  ${greeting:audience}` — this is expected, not a bug (see Gotchas).
- **Substitution, cooked.** `"$B" query --interpolated
  greeting:message` prints `hello world` — the value exactly as a
  recipe receives it (same substitution pipeline). The flag also works
  after the argument (`query greeting:message --interpolated`) and on
  `annotate` (`annotate --interpolated greeting` prints cooked values
  with their origins). `install-and-inspect`'s real part proves the
  same cooked values land on disk, and `make test` covers substitution
  semantics extensively.

## Gotchas

- `query`/`annotate` print RAW, uninterpolated values BY DEFAULT.
  Assert substituted strings only with `--interpolated`; without the
  flag the assertion will fail even when substitution works. With the
  flag, values come from the same cooked `Options.get()` pipeline
  recipes use.
- Querying a nonexistent section or key exits 1 with
  `Error: Section not found: <name>` / `Error: Key not found: <name>`
  on stderr — usable as a negative check. A bare `query foo` (no `:`)
  is NOT an error: it queries option `foo` in the `buildout` section.
  Malformed arguments — more than one `:` or an empty side, e.g.
  `a:b:c`, `:port`, `values:` — exit 1 with
  `Error: Invalid query argument: '<arg>' (expected section:option)`.
- Assignments apply to that invocation only; nothing is persisted to
  `buildout.cfg`.
- User defaults (`~/.buildout/default.cfg`, if present) can shadow
  expectations; add `-U` to any drive that must be isolated from them.
