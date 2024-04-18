from .decorators import plugfunc, worker_init, global_init
from .memory import _memory, settings
from .executor import init_plugin_system, PluginModeFlags
from .networking import create_and_start_plugin_server, create_and_start_plugin_client
from .variables import PluginVariable


# _memory = PluginMemory()
available_functions = _memory.__str__

