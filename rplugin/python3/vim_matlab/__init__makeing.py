import hashlib
import os
import datetime
import errno
import re
import time
import collections

import sys
sys.path.append(os.path.dirname(__file__))

import pynvim  # Python3용 neovim 플러그인 라이브러리

from matlab_cli_controller import MatlabCliController
from python_vim_utils import PythonVimUtils as vim_helper
import python_vim_utils


__created__ = 'Mar 01, 2015'
__license__ = 'MPL 2.0'
__author__ = 'Daeyun Shin'
__email__ = "daeyun@daeyunshin.com"

@pynvim.plugin
class VimMatlab(object):
    def __init__(self, vim):
        self.vim = vim
        python_vim_utils.vim = vim
        self.gui_controller = None
        self.cli_controller = None
        self.buffer_state = collections.defaultdict(dict)

        self.function_name_pattern = re.compile(
            r'((?:^|\n[ \t]*)(?!%)[ \t]*(?:function(?:[ \t]|\.\.\.'
            r'[ \t]*\n)(?:[^\(\n]|\.\.\.[ \t]*\n)*?|classdef(?:[ \t]'
            r'|\.\.\.[ \t]*\n)(?:[^\<\n]|\.\.\.[ \t]*\n)*?))('
            r'[a-zA-Z]\w*)((?:[ \t]|\.\.\.[ \t]*\n)*(?:\(|\<|\n|$))'
        )

    @pynvim.command('MatlabPrintCellLines', sync=True)
    def run_print_cell_lines(self):
        lines = vim_helper.get_current_matlab_cell_lines(ignore_matlab_comments=True)
        vim_helper.echo_text("\n".join(lines))

    @pynvim.command('MatlabCliRunSelection', sync=True)
    def run_selection_in_matlab_cli(self):
        if self.cli_controller is None:
            self.activate_cli()
        self.matlab_write_function_files()
        lines = vim_helper.get_selection(ignore_matlab_comments=True)
        self.cli_controller.run_code(lines)

    @pynvim.command('MatlabCliRunLine', sync=True)
    def run_current_line(self):
        if self.cli_controller is None:
            self.activate_cli()
        self.matlab_write_function_files()
        line = [vim_helper.get_current_matlab_line()]
        self.cli_controller.run_code(line)

    @pynvim.command('MatlabCliRunCell', sync=True)
    def run_cell_in_matlab_cli(self):
        if self.cli_controller is None:
            self.activate_cli()
        self.matlab_write_function_files()
        lines = vim_helper.get_current_matlab_cell_lines(ignore_matlab_comments=True)
        self.cli_controller.run_code(lines)

    @pynvim.command('MatlabCliActivateControls', sync=True)
    def activate_cli(self):
        if self.cli_controller is not None:
            return
        self.cli_controller = MatlabCliController()

    @pynvim.command('MatlabCliViewVarUnderCursor', sync=True)
    def view_var_under_cursor(self):
        if self.cli_controller is None:
            self.activate_cli()
        var = vim_helper.get_variable_under_cursor()
        if var:
            self.cli_controller.run_code([f'printVarInfo({var});'])

    @pynvim.command('MatlabCliViewSelectedVar', sync=True)
    def view_selected_var(self):
        if self.cli_controller is None:
            self.activate_cli()
        var = vim_helper.get_selection()
        if var:
            self.cli_controller.run_code([f'printVarInfo({var});'])

    @pynvim.command('MatlabCliCancel', sync=True)
    def matlab_cli_cancel(self):
        if self.cli_controller is None:
            self.activate_cli()
        self.cli_controller.send_ctrl_c()

    @pynvim.command('MatlabCliOpenInMatlabEditor', sync=True)
    def matlab_cli_open_in_matlab_editor(self):
        if self.cli_controller is None:
            self.activate_cli()
        path = vim_helper.get_current_file_path()
        self.cli_controller.open_in_matlab_editor(path)

    @pynvim.command('MatlabCliOpenWorkspace', sync=True)
    def matlab_cli_open_workspace(self):
        if self.cli_controller is None:
            self.activate_cli()
        self.cli_controller.open_workspace()

    @pynvim.command('MatlabCliHelp', sync=True)
    def matlab_cli_help(self):
        if self.cli_controller is None:
            self.activate_cli()
        var = vim_helper.get_variable_under_cursor()
        self.cli_controller.help_command(var)

    @pynvim.command('MatlabCliOpenVar', sync=True)
    def matlab_cli_open_var(self):
        if self.cli_controller is None:
            self.activate_cli()
        var = vim_helper.get_variable_under_cursor()
        self.cli_controller.openvar(var)

    @pynvim.command('MatlabWriteFunctionFiles', sync=True)
    def matlab_write_function_files(self):
        options = vim_helper.get_options()
        if 'split' in options:
            group_name = options['split'][0]
        else:
            return
        dir_path = os.path.join(
            os.path.dirname(vim_helper.get_current_file_path()), group_name)
        os.makedirs(dir_path, exist_ok=True)

        existing_filenames = [name for name in os.listdir(dir_path) if name.endswith('.m')]
        function_blocks = vim_helper.get_function_blocks()
        new_filenames = [f"{name}.m" for name in function_blocks.keys()]

        unused_filenames = set(existing_filenames) - set(new_filenames)
        for name in unused_filenames:
            os.remove(os.path.join(dir_path, name))

        for name in new_filenames:
            content = function_blocks[os.path.splitext(name)[0]].strip()
            with open(os.path.join(dir_path, name), 'w') as f:
                f.write(content)

    @pynvim.command('MatlabOpenTempScript', sync=True, nargs='*')
    def open_temp_matlab_script(self, args):
        dirname = os.path.join(os.path.expanduser('~'), '.vim-matlab/scratch/')
        os.makedirs(dirname, exist_ok=True)
        timestamp = datetime.datetime.now().strftime("%Y_%m_%d_%H_%M_%S")
        filename = f"{timestamp}_{args[0]}.m" if args else f"{timestamp}.m"
        self.vim.command(f'edit {os.path.join(dirname, filename)}')

    @pynvim.autocmd('VimLeave', pattern='*', sync=True)
    def vim_leave(self):
        if self.gui_controller is not None:
            self.gui_controller.close()

    @pynvim.autocmd('InsertEnter', pattern='*.m')
    def insert_enter(self):
        self.refresh_buffer()

    @pynvim.autocmd('BufEnter', pattern='*.m')
    def buf_enter(self):
        self.set_last_written()

    @pynvim.autocmd('BufDelete', pattern='*.m')
    def buf_delete(self):
        path = vim_helper.get_current_file_path()
        self.buffer_state.pop(path, None)

    @pynvim.autocmd('BufWrite', pattern='*.m', sync=True)
    def buf_write(self):
        self.set_last_written()
        self.matlab_write_function_files()

    def set_last_written(self):
        path = vim_helper.get_current_file_path()
        self.buffer_state[path]['last_written'] = time.time()

    def refresh_buffer(self):
        path = vim_helper.get_current_file_path()
        if time.time() - self.buffer_state[path]['last_written'] < 1 or not os.path.isfile(path):
            return
        modified = os.stat(path).st_mtime
        if modified > self.buffer_state[path]['last_written'] + 8:
            row_col = vim_helper.get_cursor()
            vim_helper.edit_file(path)
            vim_helper.set_cursor(row_col)
