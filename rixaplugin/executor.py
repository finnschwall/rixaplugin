import asyncio
from concurrent.futures import ThreadPoolExecutor, ProcessPoolExecutor, Future

from .enums import FunctionPointerType
from .memory import _memory
import functools
from enum import Flag, auto
from .utils import *
import logging
from .rixa_exceptions import FunctionNotFoundException, QueueOverflowException, PluginNotFoundException
core_log = logging.getLogger("core")

class PluginModeFlags(Flag):
    LOCAL = auto()
    THREAD = auto()
    PROCESS = auto()
    IPC_SOCKET = auto()
    NETWORK = auto()
    CLIENT = auto()
    SERVER = auto()
    JUPYTER = auto()


DebugLocal = PluginModeFlags.LOCAL | PluginModeFlags.THREAD
Server = PluginModeFlags.SERVER | PluginModeFlags.NETWORK | PluginModeFlags.THREAD


async def init_plugin_system(mode=DebugLocal, num_workers=4, debug= False, max_juypter_messages=10):
    if debug:
        asyncio.get_event_loop().set_debug(True)
        core_log.setLevel(logging.DEBUG)
    if mode & PluginModeFlags.THREAD:
        _memory.executor = ThreadPoolExecutor(max_workers=num_workers)
    if mode & PluginModeFlags.LOCAL:
        pass
    if mode & PluginModeFlags.JUPYTER:
        from .rixalogger import JupyterLoggingHandler, RIXAFilter, RIXALogger
        jupyter_handler = JupyterLoggingHandler(max_juypter_messages)

        loggers = [logging.getLogger(name) for name in logging.root.manager.loggerDict]

        # for logger in loggers:
        #     if isinstance(logger, RIXALogger):
        #         logger.addHandler(jupyter_handler)
        root_logger = logging.getLogger()
        if type(root_logger.handlers[0]) == logging.StreamHandler:
            root_logger.removeHandler(root_logger.handlers[0])
        root_logger.addHandler(jupyter_handler)
        core_log.info("Jupyter logging enabled")

        # for logger_name, logger_obj in logging.Logger.manager.loggerDict.items():
        #     if isinstance(logger_obj, logging.Logger):
        #         print(logger_obj.name, logger_obj.handlers, logger_obj.level)
                # if logger_obj.level > 0:

                    # print(logger_obj.__dict__)
                    # logger_obj.addHandler(jupyter_handler)

                # if any(isinstance(filter, RIXAFilter) for handler in logger_obj.handlers for filter in handler.filters):
                #     print(dir(logger_obj))
                #     print(logger_obj.name)


    # if mode & PluginModeFlags.SERVER:
    #     fut = asyncio.create_task(start_plugin_server(port=port))
    #     await supervise_future(fut)
    # else:
    #     raise Exception("Improper config!")
    _memory.event_loop = asyncio.get_event_loop()
    _memory.mode = mode
    _memory.plugin_system_active = True

async def execute_sync(pointer, args, kwargs, return_future=False):
    """
    Runs a sync function in the plugin system.

    For sync-sync calls, do not use this function, but rather call the function directly.
    :param plugin_entry:
    :param args:
    :param kwargs:
    :param return_future:
    :return:
    """
    if _memory.max_queue < _memory.executor.queue.qsize():
        raise QueueOverflowException()
    fun = functools.partial(pointer, *args, **kwargs)
    future = _memory.event_loop.run_in_executor(_memory.executor, fun)#_memory.executor.submit(pointer, *args, **kwargs)
    if return_future:
        return future
    else:
        await supervise_future(future)


async def execute_networked(plugin_entry, args, kwargs, request_id):
    """
    Runs a function locally that has been requested from a remote source.

    This function sets appropriate flags, callbacks etc. to ensure mirroring to the remote source.
    Usually this does not need to be called directly.
    :param plugin_entry:
    :param args:
    :param kwargs:
    :param request_id:
    :return:
    """

    pointer = plugin_entry["pointer"]

    fun = functools.partial(pointer, *args, **kwargs)
    future = _memory.event_loop.run_in_executor(_memory.executor, fun)
    remote_origin = plugin_entry["remote_origin"]
    remote_identity = plugin_entry["remote_id"]
    try:
        return_val = await future
        await remote_origin.send_return(remote_identity, request_id, return_val)
    except Exception as e:
        core_log.exception(f"Error during execution. ID: {request_id}")
        await remote_origin.send_exception(remote_identity, request_id, e)


async def execute(plugin_entry, args, kwargs, return_future=False):
    if not _memory.plugin_system_active:
        raise Exception("Plugin system not initialized")
    if plugin_entry["type"] & FunctionPointerType.LOCAL:
        if plugin_entry["type"] & FunctionPointerType.SYNC:
            return await execute_sync(plugin_entry["pointer"], args, kwargs, return_future=return_future)
        else:

    elif plugin_entry["type"] & FunctionPointerType.REMOTE:
        if plugin_entry["type"] & FunctionPointerType.CLIENT:
            return await _memory.server.call_remote_function(plugin_entry, args=args, kwargs=kwargs, one_way=return_future,
                                   return_time_estimate=True)
        elif plugin_entry["type"] & FunctionPointerType.SERVER:
            return await _memory.server.execute_remote(entry["remote_id"], entry["name"], args, kwargs, request_id, return_future=return_future)
    else:
        raise Exception("Oh no!")


def get_plugin_entry(name, plugin_name = None):
    if not plugin_name:
        filtered_entries = [d for d in _memory.function_list if d.get("name") == name]
        if len(filtered_entries) > 1:
            raise Exception("Multiple functions with same name found. Specify plugin name to resolve ambiguity.")
        if len(filtered_entries) == 0:
            raise FunctionNotFoundException(name)
        return filtered_entries[0]
    else:
        plugin_entry = _memory.plugins.get(plugin_name, None)
        if not plugin_entry:
            raise PluginNotFoundException(plugin_name)
        filtered_entries = [d for d in plugin_entry["functions"] if d.get("name") == name]
        if len(filtered_entries) == 0:
            raise FunctionNotFoundException(f"Plugin '{plugin_name}' found, but not function:", name)
        return filtered_entries[0]

# async def execute_local(name, args, kwargs,  identity, request_id, call_type, return_future=False):
#     if not _memory.plugin_system_active:
#         raise Exception("Plugin system not initialized")
#     entry = _memory.find_function_by_name(name)
#     if not entry:
#         raise FunctionNotFoundException(name)
#     pointer = entry["pointer"]
#     fun = functools.partial(pointer, *args, **kwargs)
#     future = _memory.event_loop.run_in_executor(_memory.executor, fun, request_id, identity, call_type)
#     if return_future:
#         return future
#     try:
#         return_val = await future
#         await _memory.server.send_return(identity, request_id, return_val)
#     except Exception as e:
#         core_log.exception(f"Exception occurred during local execution of function \"{name}\"")
#         if call_type == 3:
#             await _memory.server.send_exception(identity, request_id, e)


# def _run_job(fun, sender):
#     ret = None
#     try:
#         ret = fun()
#     except Exception as e:
#         print(e)
#     if ret:
#         return ret


# def execute_function(name, *args, **kwargs):
#     if not _memory.plugin_system_active:
#         raise Exception("Plugin system not initialized")
#     if _memory.mode & PluginModeFlags.LOCAL:
#         execute_local(name, *args, **kwargs)

