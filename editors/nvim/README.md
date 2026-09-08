# nvim-treesitter support for zc.buildout configs

Tree-sitter highlighting for `buildout.cfg` and friends, driven by the
[tree-sitter-buildout](../../tree-sitter-buildout/) grammar. This directory
is a self-contained Neovim plugin:

```
editors/nvim/
├── Makefile                  # compiles parser/buildout.so (plain cc, no tree-sitter CLI needed)
├── ftdetect/buildout.lua     # filetype detection (buildout.cfg & co.)
├── ftplugin/buildout.lua     # starts vim.treesitter on buildout buffers
├── queries/buildout/
│   ├── highlights.scm        # node → capture mappings (@comment, @property, …)
│   └── injections.scm        # old-style conditions are injected as Python
└── tests/sample.cfg          # demo file for a quick visual / :Inspect check
```

What you get: section names as headings, option names as properties,
`${section:option}` substitutions as variables, `$$` as an escape, `<=` /
`=>` as import/directive keywords, comments, and — inside `[name: …]`
conditions — PEP 508 markers with their environment variables as
`variable.builtin`, while old-style arbitrary-Python conditions are
highlighted by the real Python grammar via injection (when the python
parser is installed; the injection is skipped silently otherwise).

The parser is ABI 14 and works with Neovim ≥ 0.10 (verified on 0.12.5).

## Install — Nix / Home Manager

One derivation compiles the parser and packages the plugin; add it to
`programs.neovim.plugins` (tested on nixpkgs-unstable + Neovim 0.12.5):

```nix
{ pkgs, ... }:
let
  # absolute path to a local zc.buildout checkout (impure but handy),
  # or a fetchFromGitHub once the branch lands upstream
  buildoutCheckout = /Users/you/co/buildout-grammar;
  buildoutNvim = pkgs.stdenv.mkDerivation {
    pname = "nvim-treesitter-buildout";
    version = "unstable-2026-09-08";
    src = buildoutCheckout + /editors/nvim;
    parserSrc = buildoutCheckout + /tree-sitter-buildout/src;
    buildPhase = ''
      runHook preBuild
      mkdir -p parser
      cc -O2 -shared -fPIC -o parser/buildout.so \
        "$parserSrc/parser.c" -I "$parserSrc"
      runHook postBuild
    '';
    installPhase = ''
      runHook preInstall
      mkdir -p $out
      cp -r ftdetect ftplugin queries parser $out/
      runHook postInstall
    '';
  };
in
{
  programs.neovim = {
    enable = true;
    plugins = with pkgs.vimPlugins; [
      # … your existing plugins (nvim-treesitter etc.) …
      { plugin = buildoutNvim; }
    ];
  };
}
```

(Why not `vimUtils.buildVimPlugin`? It forces its own installPhase, which
would copy the entire checkout — including `venvs/` — into the store.
Two small source paths keep the derivation minimal and sandbox-clean.)

Then `darwin-rebuild switch` (or `home-manager switch`). No extra Lua:
Neovim finds the parser in the plugin's `parser/` directory and the
queries in `queries/buildout/`, and the bundled `ftdetect` sets the
`buildout` filetype. Coexists fine with a bare `nvim-treesitter` plugin —
highlighting itself is done by Neovim core.

Optional: for Python highlighting inside old-style conditions, also have
the python grammar installed, e.g. via nvim-treesitter
(`:TSInstall python`) or nixpkgs
(`pkgs.vimPlugins.nvim-treesitter.withPlugins (p: [ p.python ])`).

## Install — lazy.nvim

```lua
{
  dir = '~/co/buildout-grammar/editors/nvim',
  build = 'make',   -- compiles parser/buildout.so with cc
}
```

## Install — manual (any Neovim)

```sh
cd ~/co/buildout-grammar/editors/nvim
make                                        # builds parser/buildout.so
ln -s "$PWD" ~/.config/nvim/pack/local/start/buildout
```

## Filetypes

Detected by basename: `buildout.cfg`, `.buildout.cfg`, `versions.cfg`,
`default.cfg`, `base.cfg`, `development.cfg`, `production.cfg`,
`deployment.cfg`, `staging.cfg`, `testing.cfg`. To light up other names:

```lua
vim.api.nvim_create_autocmd({ 'BufRead', 'BufNewFile' }, {
  pattern = 'constraints.cfg',
  callback = function() vim.bo.filetype = 'buildout' end,
})
```

## Tests

```sh
make test
```

`tests/run.sh` builds the parser if needed, then runs `tests/spec.lua`
in a clean-room Neovim (`--headless --clean`, only this plugin on the
runtimepath). The spec asserts:

- filetype detection fires for `buildout.cfg` and `versions.cfg`, and
  leaves an unrelated `random.cfg` alone
- the parser loads (ABI compatibility with the running Neovim)
- the ftplugin starts the tree-sitter highlighter
- every capture group used by `queries/buildout/highlights.scm` lands
  at least once on `tests/sample.cfg`
- `injections.scm` targets exactly the old-style condition text
  (`sys.version_info[0] == 3`) and nothing else — PEP 508 marker
  expressions are deliberately not injected as Python

When the tree-sitter CLI is on `PATH`, `run.sh` additionally compiles
the queries against the grammar with `tree-sitter query`, which fails
on stale node names after a grammar regeneration. (Without the CLI,
Neovim itself still fails the spec: it refuses to compile a query that
references a node the grammar doesn't have.) The `nvim-plugin` job in
`.github/workflows/lint.yml` runs `make test` on every push.

## After grammar changes

The parser is a build artifact: when `tree-sitter-buildout` is
regenerated, rebuild with `make clean && make` here (or rebuild your
Home Manager generation). `:Inspect` inside a buildout buffer shows the
captures under the cursor.
