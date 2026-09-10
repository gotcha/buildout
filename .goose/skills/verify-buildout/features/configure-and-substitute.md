# Configure and substitute

Users compose configuration through INI sections, `${section:option}`
substitutions, `extends`, and command-line assignments of the form
`section:option=value` that override file values. `query` and
`annotate` expose what the configuration says and where each value
came from.

## Sub-features

- `assign-override` — a `section:option=value` command-line assignment
  overrides the config file value.
- `annotate-origin` — `annotate` attributes each value to its source
  (file, DEFAULT_VALUE, COMMAND_LINE_VALUE).
- `substitute-raw-vs-cooked` — `${...}` substitution exists in the
  config language; CLI views show raw templates, recipes get cooked
  values.

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
- **Substitution template.** `"$B" query greeting:message` prints the
  RAW template `hello ${greeting:audience}` — this is expected, not a
  bug (see Gotchas). Cooked substitution is proven through
  `install-and-inspect`'s real part (recipes receive substituted
  values) and through the suites (`make test` covers substitution
  semantics extensively).

## Gotchas

- `query`/`annotate` print RAW, uninterpolated values. Never assert a
  substituted string from `query` — the assertion will fail even when
  substitution works.
- Querying a nonexistent key exits non-zero with
  `Error: Section not found: <name>` on stderr — usable as a negative
  check.
- Assignments apply to that invocation only; nothing is persisted to
  `buildout.cfg`.
- User defaults (`~/.buildout/default.cfg`, if present) can shadow
  expectations; add `-U` to any drive that must be isolated from them.
