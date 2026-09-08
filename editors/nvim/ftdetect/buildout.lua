-- Detect buildout configuration files.
--
-- Conservative basename list: these are the conventional file names used
-- by zc.buildout projects (buildout.cfg plus the classic
-- deployment/development/… layered configs). Add your own names with an
-- extra autocmd, e.g.:
--
--   vim.api.nvim_create_autocmd({ 'BufRead', 'BufNewFile' }, {
--     pattern = 'constraints.cfg',
--     callback = function() vim.bo.filetype = 'buildout' end,
--   })
vim.filetype.add({
  filename = {
    ['buildout.cfg'] = 'buildout',
    ['.buildout.cfg'] = 'buildout',
    ['versions.cfg'] = 'buildout',
    ['default.cfg'] = 'buildout',
    ['base.cfg'] = 'buildout',
    ['development.cfg'] = 'buildout',
    ['production.cfg'] = 'buildout',
    ['deployment.cfg'] = 'buildout',
    ['staging.cfg'] = 'buildout',
    ['testing.cfg'] = 'buildout',
  },
})
