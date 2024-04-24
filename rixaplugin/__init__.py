import threading
from . import decorators
from .internal.executor import init_plugin_system, execute, execute_code
from .data_structures.enums import PluginModeFlags
from .internal.networking import create_and_start_plugin_server, create_and_start_plugin_client
from .internal.memory import _memory, get_function_entry
from .internal.utils import supervise_future

from .data_structures import variables
get_state_info = _memory.__str__
get_plugin_info = _memory.pretty_print_plugin

worker_context = threading.local()
