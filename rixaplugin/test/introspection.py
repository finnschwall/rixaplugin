from rixaplugin.memory import _memory
from rixaplugin.executor import get_function_entry
import pprint
from rixaplugin.decorators import plugfunc

# @plugfunc()
# async def intro_function(func_name, plugin_name = None):
#     entry = get_function_entry(func_name, plugin_name)
#     entry_str = pprint.pformat(entry, indent=2)
#     return entry_str

@plugfunc()
async def help(func_name=None, plugin_name = None):
    if func_name:
        entry = get_function_entry(func_name, plugin_name)
        entry_str = pprint.pformat(entry, indent=4)
        return entry_str
    elif plugin_name:
        return _memory.pretty_print_plugin(plugin_name)
    else:
        return _memory.pretty_print_plugins()

