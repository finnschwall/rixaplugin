from rixaplugin.internal.memory import _memory, get_function_entry_by_name

import pprint
from rixaplugin.decorators import plugfunc
from rixaplugin.internal import api

@plugfunc(local_only=True)
async def help(func_name=None, plugin_name = None):
    if func_name:
        entry = get_function_entry_by_name(func_name, plugin_name)
        entry_str = pprint.pformat(entry, indent=4)
        return entry_str
    elif plugin_name:
        return _memory.pretty_print_plugin(plugin_name)
    else:
        return _memory.pretty_print_filtered_plugins(api.get_api().scope)


@plugfunc(local_only=True)
async def get_code(func_name, plugin_name = None):
    entry = get_function_entry_by_name(func_name, plugin_name)
    if "code" not in entry:
        return "No code stored for this function"
    return entry["code"]
