#!/usr/bin/env bash
# Headless test harness for the buildout nvim plugin.
#   - builds parser/buildout.so if missing
#   - runs tests/spec.lua in a clean-room nvim (--headless --clean, plugin on rtp)
#   - validates the queries against the grammar with the tree-sitter CLI
#     when it is on PATH (regen-drift guard)
set -euo pipefail
cd "$(dirname "$0")/.."
PLUGIN_DIR="$PWD"

if [ ! -f parser/buildout.so ]; then
  echo "== building parser =="
  make parser/buildout.so
fi

TMP="$(mktemp -d "${TMPDIR:-/tmp}/buildout-nvim-test.XXXXXX")"
trap 'rm -rf "$TMP"' EXIT
export BUILDOUT_PLUGIN_TEST_TMP="$TMP"
export BUILDOUT_PLUGIN_TEST_SAMPLE="$PLUGIN_DIR/tests/sample.cfg"

echo "== nvim headless spec =="
nvim --headless --clean \
  --cmd "set rtp+=$PLUGIN_DIR" \
  -c "filetype on" \
  -c "luafile $PLUGIN_DIR/tests/spec.lua"

echo "== query validation (tree-sitter CLI) =="
if command -v tree-sitter >/dev/null 2>&1; then
  GRAMMAR_DIR="$PLUGIN_DIR/../../tree-sitter-buildout"
  for query in "$PLUGIN_DIR"/queries/buildout/*.scm; do
    (cd "$GRAMMAR_DIR" && tree-sitter query "$query" "$PLUGIN_DIR/tests/sample.cfg" >/dev/null)
    echo "OK ${query#"$PLUGIN_DIR"/}"
  done
else
  echo "SKIP: tree-sitter CLI not on PATH — queries not checked against the grammar"
  echo "      (nvim itself still fails above if a query names a node the grammar lacks)"
fi

echo "ALL TESTS PASSED"
