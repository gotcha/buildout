# Build the tree-sitter-buildout parser for Neovim.
#
# Neovim looks for <language>.so in every parser/ directory on its
# runtimepath, so the product of this Makefile is parser/buildout.so.
#
# Mirrors the compile line used by the packaged linter
# (src/zc/buildout/lint.py): plain C, no tree-sitter CLI required.

PARSER_C := ../../tree-sitter-buildout/src/parser.c
OUT := parser/buildout.so
CC ?= cc

$(OUT): $(PARSER_C)
	mkdir -p parser
	$(CC) -O2 -shared -fPIC -o $@ $(PARSER_C) -I $(dir $(PARSER_C))

.PHONY: clean
clean:
	rm -rf parser
