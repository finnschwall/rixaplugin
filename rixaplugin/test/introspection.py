from rixaplugin.internal.memory import _memory
from rixaplugin.internal.executor import get_function_entry
import pprint
from rixaplugin.decorators import plugfunc


@plugfunc(local_only=True)
async def help(func_name=None, plugin_name = None):
    if func_name:
        entry = get_function_entry(func_name, plugin_name)
        entry_str = pprint.pformat(entry, indent=4)
        return entry_str
    elif plugin_name:
        return _memory.pretty_print_plugin(plugin_name)
    else:
        return _memory.pretty_print_plugins()


@plugfunc(local_only=True)
async def get_code(func_name, plugin_name = None):
    entry = get_function_entry(func_name, plugin_name)
    if "code" not in entry:
        return "No code stored for this function"
    return entry["code"]
