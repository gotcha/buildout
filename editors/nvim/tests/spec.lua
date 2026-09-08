-- Headless assertions for the buildout nvim plugin.
-- Not run directly: tests/run.sh sets the env vars and invokes nvim.
--
-- Env:
--   BUILDOUT_PLUGIN_TEST_TMP     writable scratch dir
--   BUILDOUT_PLUGIN_TEST_SAMPLE  path of the sample .cfg to open

local tmp = assert(vim.env.BUILDOUT_PLUGIN_TEST_TMP, 'BUILDOUT_PLUGIN_TEST_TMP not set')
local sample = assert(vim.env.BUILDOUT_PLUGIN_TEST_SAMPLE, 'BUILDOUT_PLUGIN_TEST_SAMPLE not set')

local failures = 0
local function check(name, ok, detail)
  if ok then
    print('PASS ' .. name)
  else
    failures = failures + 1
    print('FAIL ' .. name .. (detail ~= nil and (' -- ' .. tostring(detail)) or ''))
  end
end

local lines = vim.fn.readfile(sample)
local function open_as(name)
  local path = tmp .. '/' .. name
  vim.fn.writefile(lines, path)
  vim.cmd('edit ' .. vim.fn.fnameescape(path))
end

-- 1. Filetype detection -------------------------------------------------------
open_as('buildout.cfg')
check('ftdetect: buildout.cfg -> buildout', vim.bo.filetype == 'buildout', vim.bo.filetype)
local buf = vim.api.nvim_get_current_buf()

-- 2. Parser loads (catches ABI mismatches and a missing parser/buildout.so) ---
local pok, parser = pcall(vim.treesitter.get_parser, buf, 'buildout')
check('parser: loads', pok and parser ~= nil, pok and nil or parser)

-- 3. ftplugin started the treesitter highlighter ------------------------------
check('ftplugin: highlighter active', vim.treesitter.highlighter.active[buf] ~= nil)

-- 4. Highlight captures land on the sample ------------------------------------
--    (a stale node name in highlights.scm makes the whole query fail to
--    compile, so this also guards query/grammar drift)
local qok, q = pcall(vim.treesitter.query.get, 'buildout', 'highlights')
check('queries: highlights.scm compiles', qok and q ~= nil, qok and nil or q)

local counts, total = {}, 0
if qok and pok then
  local root = parser:parse()[1]:root()
  for id in q:iter_captures(root, buf) do
    local name = q.captures[id]
    counts[name] = (counts[name] or 0) + 1
    total = total + 1
  end
end
for _, name in ipairs({
  'comment',
  'markup.heading',
  'property',
  'operator',
  'string',
  'string.escape',
  'variable.member',
  'variable.builtin',
  'keyword.import',
  'keyword.directive',
  'keyword.operator',
  'punctuation.bracket',
  'punctuation.delimiter',
}) do
  check('capture: ' .. name .. ' present', (counts[name] or 0) > 0)
end
check('capture: sane total (>= 30)', total >= 30, total)
-- Regression: ${...} must be a substitution on ANY line of a multiline
-- value, not just the first (sample.cfg has one per line in `eggs`).
check(
  'capture: variable.member on first AND continuation line',
  (counts['variable.member'] or 0) >= 2,
  counts['variable.member']
)

-- 5. Injection: old-style condition_body -> python, marker expression NOT -----
local iok, iq = pcall(vim.treesitter.query.get, 'buildout', 'injections')
check('queries: injections.scm compiles', iok and iq ~= nil, iok and nil or iq)

local targets = {}
if iok and pok then
  local root = parser:parse()[1]:root()
  for id, node in iq:iter_captures(root, buf) do
    if iq.captures[id] == 'injection.content' then
      targets[#targets + 1] = vim.treesitter.get_node_text(node, buf)
    end
  end
end
check('injection: exactly one target', #targets == 1, table.concat(targets, ' | '))
check(
  'injection: targets the old-style condition',
  #targets == 1 and targets[1]:find('sys.version_info', 1, true) ~= nil,
  targets[1]
)

-- 6. More filetype cases ------------------------------------------------------
open_as('versions.cfg')
check('ftdetect: versions.cfg -> buildout', vim.bo.filetype == 'buildout', vim.bo.filetype)
open_as('random.cfg')
check('ftdetect: random.cfg left alone', vim.bo.filetype ~= 'buildout', vim.bo.filetype)

if failures > 0 then
  print(('RESULT: %d failure(s)'):format(failures))
  vim.cmd('cquit 1')
end
print('RESULT: all checks passed')
vim.cmd('qa!')
