from rixaplugin.internal.memory import _memory, get_function_entry_by_name

import pprint
from rixaplugin.decorators import plugfunc
from rixaplugin.internal import api
from rixaplugin.pylot.python_parsing import generate_python_doc


@plugfunc(local_only=True)
async def help(func_name=None, plugin_name = None):
    if func_name:
        entry = get_function_entry_by_name(func_name, plugin_name)
        # entry_str = pprint.pformat(entry, indent=4)
        entry_str = generate_python_doc(entry, include_docstr=True, tabulators=1)
        return entry_str
    elif plugin_name:
        return _memory.pretty_print_plugin(plugin_name, include_docstr=False)
    else:
        return _memory.pretty_print_filtered_plugins(api.get_api().scope, include_docstr=False,
                                                     include_plugin_meta=False)


@plugfunc(local_only=True)
async def get_code(func_name, plugin_name = None):
    entry = get_function_entry_by_name(func_name, plugin_name)
    if "code" not in entry:
        return "No code stored for this function"
    return entry["code"]

