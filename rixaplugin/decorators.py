from .python_parsing import function_signature_to_dict
from warnings import warn
from .memory import _memory
# _memory = PluginMemory()
import asyncio
import functools
import contextvars

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


def plugfunc(api_as_arg=True, api_as_kwarg=False):
    def plugin_method(original_function):
        dic_entry = function_signature_to_dict(original_function)
        dic_entry["type"] = "local"
        dic_entry["pointer"] = original_function

        is_coroutine = asyncio.iscoroutinefunction(original_function)

        _memory.add_function(dic_entry)

        # if is_coroutine:
        #     @functools.wraps(original_function)
        #     async def wrapper_func(*args, **kwargs):
        #         return await original_function(*args, **kwargs)
        # else:
        #     @functools.wraps(original_function)
        #     def wrapper_func(*args, **kwargs):
        #         return original_function(*args, **kwargs)

        return original_function

    return plugin_method


def worker_init():
    def plugin_method(original_function):
        if _memory.worker_init is not None:
            warn("Worker init function already exists!\nWill be overriden")
        _memory.worker_init = original_function
        return original_function

    return plugin_method


def global_init():
    def plugin_method(original_function):
        if _memory.global_init is not None:
            warn("Global init function already exists!\nWill be overriden")
        _memory.global_init = original_function
        return original_function

    return plugin_method

