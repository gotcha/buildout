-- Start tree-sitter highlighting for buildout files.
-- pcall: silently stay with regex-less plain text when the parser is not
-- installed (see README, "Install").
pcall(vim.treesitter.start)
