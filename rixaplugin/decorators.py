from rixaplugin.pylot.python_parsing import function_signature_to_dict
from warnings import warn
from rixaplugin.internal.memory import _memory
import asyncio
import functools
from rixaplugin.data_structures.enums import FunctionPointerType
import inspect
# def universal_decorator(func):
#     @functools.wraps(func)
#     async def wrapper_async(*args, **kwargs):
#         # Handle async function
#         return await func(*args, **kwargs)
#
#     @functools.wraps(func)
#     def wrapper_sync(*args, **kwargs):
#         # Handle sync function
#         return func(*args, **kwargs)
#
#     if asyncio.iscoroutinefunction(func):
#         return wrapper_async
#     else:
#         return wrapper_sync


def plugfunc(local_only=False):
    def plugin_method(original_function):
        if _memory.plugin_system_active:
            raise Exception("Cant add plugins when plugin system has been started!")
        dic_entry = function_signature_to_dict(original_function)
        dic_entry["type"] = FunctionPointerType.LOCAL
        dic_entry["pointer"] = original_function
        is_coroutine = asyncio.iscoroutinefunction(original_function)
        if is_coroutine:
            dic_entry["type"] |= FunctionPointerType.ASYNC
        else:
            dic_entry["type"] |= FunctionPointerType.SYNC
        if local_only:
            dic_entry["type"] |= FunctionPointerType.LOCAL_ONLY
        # dic_entry["coroutine"] = asyncio.iscoroutinefunction(original_function)
        fname = original_function.__module__.split(".")
        if len(fname) > 1:
            if fname[-1] == "py":
                dic_entry["plugin_name"] = fname[-2]
            else:
                dic_entry["plugin_name"] = fname[-1]
        else:
            dic_entry["plugin_name"] = fname[0]
        # print(inspect.getsourcefile(original_function))
        _memory.add_function(dic_entry)

        if is_coroutine:
            @functools.wraps(original_function)
            async def wrapper_func(*args, **kwargs):
                return await original_function(*args, **kwargs)
        else:
            @functools.wraps(original_function)
            def wrapper_func(*args, **kwargs):
                return original_function(*args, **kwargs)
        plugin_method._original_function = original_function
        return wrapper_func

    return plugin_method


def worker_init():
    def plugin_method(original_function):
        # if _memory.worker_init is not None:
        #     warn("Worker init function already exists!\nWill be overriden")
        _memory.worker_init.append(original_function)
        return original_function

    return plugin_method


def global_init():
    def plugin_method(original_function):
        if _memory.global_init is not None:
            warn("Global init function already exists!\nWill be overriden")
        _memory.global_init.append(original_function)
        return original_function

    return plugin_method

