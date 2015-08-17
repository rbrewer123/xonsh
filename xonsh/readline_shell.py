"""The readline based xonsh shell"""
import os
import builtins
from cmd import Cmd
from warnings import warn

from xonsh.base_shell import BaseShell

RL_COMPLETION_SUPPRESS_APPEND = RL_LIB = None
RL_CAN_RESIZE = False


def setup_readline():
    """Sets up the readline module and completion supression, if available."""
    global RL_COMPLETION_SUPPRESS_APPEND, RL_LIB, RL_CAN_RESIZE
    if RL_COMPLETION_SUPPRESS_APPEND is not None:
        return
    try:
        import readline
    except ImportError:
        return
    import ctypes
    import ctypes.util
    readline.set_completer_delims(' \t\n')
    if not readline.__file__.endswith('.py'):
        RL_LIB = lib = ctypes.cdll.LoadLibrary(readline.__file__)
        try:
            RL_COMPLETION_SUPPRESS_APPEND = ctypes.c_int.in_dll(
                lib, 'rl_completion_suppress_append')
        except ValueError:
            # not all versions of readline have this symbol, ie Macs sometimes
            RL_COMPLETION_SUPPRESS_APPEND = None
        RL_CAN_RESIZE = hasattr(lib, 'rl_reset_screen_size')
    # reads in history
    env = builtins.__xonsh_env__
    hf = env.get('XONSH_HISTORY_FILE', os.path.expanduser('~/.xonsh_history'))
    if os.path.isfile(hf):
        try:
            readline.read_history_file(hf)
        except PermissionError:
            warn('do not have read permissions for ' + hf, RuntimeWarning)
    hs = env.get('XONSH_HISTORY_SIZE', 8128)
    readline.set_history_length(hs)
    # sets up IPython-like history matching with up and down
    readline.parse_and_bind('"\e[B": history-search-forward')
    readline.parse_and_bind('"\e[A": history-search-backward')
    # Setup Shift-Tab to indent
    readline.parse_and_bind('"\e[Z": "{0}"'.format(env.get('INDENT', '')))

    # handle tab completion differences found in libedit readline compatibility
    # as discussed at http://stackoverflow.com/a/7116997
    if readline.__doc__ and 'libedit' in readline.__doc__:
        readline.parse_and_bind("bind ^I rl_complete")
    else:
        readline.parse_and_bind("tab: complete")


def teardown_readline():
    """Tears down up the readline module, if available."""
    try:
        import readline
    except ImportError:
        return
    env = builtins.__xonsh_env__
    hs = env.get('XONSH_HISTORY_SIZE', 8128)
    readline.set_history_length(hs)
    hf = env.get('XONSH_HISTORY_FILE', os.path.expanduser('~/.xonsh_history'))
    try:
        readline.write_history_file(hf)
    except PermissionError:
        warn('do not have write permissions for ' + hf, RuntimeWarning)


def rl_completion_suppress_append(val=1):
    """Sets the rl_completion_suppress_append varaiable, if possible.
    A value of 1 (default) means to suppress, a value of 0 means to enable.
    """
    if RL_COMPLETION_SUPPRESS_APPEND is None:
        return
    RL_COMPLETION_SUPPRESS_APPEND.value = val


def _insert_text_func(s, readline):
    """Creates a function to insert text via readline."""
    def inserter():
        readline.insert_text(s)
        readline.redisplay()
    return inserter


DEDENT_TOKENS = frozenset(['raise', 'return', 'pass', 'break', 'continue'])


class ReadlineShell(BaseShell, Cmd):
    """The readline based xonsh shell."""

    def __init__(self, completekey='tab', stdin=None, stdout=None, **kwargs):
        super().__init__(completekey=completekey,
                         stdin=stdin,
                         stdout=stdout,
                         **kwargs)
        setup_readline()
        self._current_indent = ''

    def __del__(self):
        teardown_readline()

    def parseline(self, line):
        """Overridden to no-op."""
        return '', line, line

    def completedefault(self, text, line, begidx, endidx):
        """Implements tab-completion for text."""
        rl_completion_suppress_append()  # this needs to be called each time
        return self.completer.complete(text, line,
                                       begidx, endidx,
                                       ctx=self.ctx)

    # tab complete on first index too
    completenames = completedefault

    def postcmd(self, stop, line):
        """Called just before execution of line. For readline, this handles the
        automatic indentation of code blocks.
        """
        try:
            import readline
        except ImportError:
            return stop
        if self.need_more_lines:
            if len(line.strip()) == 0:
                readline.set_pre_input_hook(None)
                self._current_indent = ''
            elif line.rstrip()[-1] == ':':
                ind = line[:len(line) - len(line.lstrip())]
                ind += builtins.__xonsh_env__.get('INDENT', '')
                readline.set_pre_input_hook(_insert_text_func(ind, readline))
                self._current_indent = ind
            elif line.split(maxsplit=1)[0] in DEDENT_TOKENS:
                env = builtins.__xonsh_env__
                ind = self._current_indent[:-len(env.get('INDENT', ''))]
                readline.set_pre_input_hook(_insert_text_func(ind, readline))
                self._current_indent = ind
            else:
                ind = line[:len(line) - len(line.lstrip())]
                if ind != self._current_indent:
                    insert_func = _insert_text_func(ind, readline)
                    readline.set_pre_input_hook(insert_func)
                    self._current_indent = ind
        else:
            readline.set_pre_input_hook(None)
        return stop

    def cmdloop(self, intro=None):
        while not builtins.__xonsh_exit__:
            try:
                super().cmdloop(intro=intro)
            except KeyboardInterrupt:
                print()  # Gives a newline
                self.reset_buffer()
                intro = None

    @property
    def prompt(self):
        """Obtains the current prompt string."""
        global RL_LIB, RL_CAN_RESIZE
        if RL_CAN_RESIZE:
            # This is needed to support some system where line-wrapping doesn't
            # work. This is a bug in upstream Python, or possibly readline.
            RL_LIB.rl_reset_screen_size()
        return super().prompt
