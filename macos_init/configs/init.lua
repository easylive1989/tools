vim.keymap.set('n', 'll', '$', { noremap = true })
vim.keymap.set('n', 'hh', '^', { noremap = true })
vim.keymap.set('n', 'z;', '$a;', { noremap = true })
vim.keymap.set('n', 'z,', '$a,', { noremap = true })
vim.keymap.set('n', 'zw', 'vf(%', { noremap = true })
vim.keymap.set('n', 'zq', 'vf{%', { noremap = true })

if vim.g.vscode then
    local fold = {
        fold = function()
            vim.fn.VSCodeNotify("editor.fold")
        end,
        unfold = function()
            vim.fn.VSCodeNotify("editor.unfold")
        end,
    }

    local refactor = {
        rename = function()
            vim.fn.VSCodeNotify("editor.action.rename")
        end,
    }

    local close = {
        all = function()
            vim.fn.VSCodeNotify("workbench.action.closeAllEditors")
        end,
        current = function()
            vim.fn.VSCodeNotify("workbench.action.closeActiveEditor")
        end,
    }

    local dart = {
        run = function()
            vim.fn.VSCodeNotify("workbench.action.debug.run")
        end,
        test = function()
            vim.fn.VSCodeNotify("testing.runAll")
        end,
        build = function()
            vim.fn.VSCodeNotify("workbench.action.tasks.runTask", "build:runner")
        end,
        buildClean = function()
            vim.fn.VSCodeNotify("workbench.action.tasks.runTask", "build:runner:clean")
        end,
    }

    local nav = {
        definition = function()
            vim.fn.VSCodeNotify("editor.action.revealDefinition")
        end,
        back = function()
            vim.fn.VSCodeNotify("workbench.action.navigateBack")
        end,
    }

    vim.keymap.set('n', 'ze', fold.unfold)
    vim.keymap.set('n', 'zc', fold.fold)

    vim.keymap.set('n', 'qa', close.all)
    vim.keymap.set('n', 'qq', close.current)

    vim.keymap.set('n', 'zrr', refactor.rename)
    vim.keymap.set('n', 'zra', dart.run)
    vim.keymap.set('n', 'zrt', dart.test)
    vim.keymap.set('n', 'zrb', dart.build)
    vim.keymap.set('n', 'zrbb', dart.buildClean)

    vim.keymap.set('n', 'zf', nav.definition)
    vim.keymap.set('n', 'zk', nav.back)
else
    -- ordinary Neovim
end