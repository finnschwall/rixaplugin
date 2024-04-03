import asyncio
from concurrent.futures import ThreadPoolExecutor, ProcessPoolExecutor, Future
from .memory import _memory
import functools
from enum import Flag, auto
from .utils import *
import logging

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


async def init_plugin_system(mode=DebugLocal, num_workers=4, debug= False):
    if debug:
        asyncio.get_event_loop().set_debug(True)
        core_log.setLevel(logging.DEBUG)
    if mode & PluginModeFlags.THREAD:
        _memory.executor = ThreadPoolExecutor(max_workers=num_workers)
    if mode & PluginModeFlags.LOCAL:
        pass
    # if mode & PluginModeFlags.SERVER:
    #     fut = asyncio.create_task(start_plugin_server(port=port))
    #     await supervise_future(fut)
    # else:
    #     raise Exception("Improper config!")
    _memory.event_loop = asyncio.get_event_loop()
    _memory.mode = mode
    _memory.plugin_system_active = True




async def execute_local(name, args, kwargs,  identity, request_id, call_type, return_future=False):
    if not _memory.plugin_system_active:
        raise Exception("Plugin system not initialized")
    entry = _memory.find_function_by_name(name)
    if not entry:
        raise FunctionNotFoundException(name)
    pointer = entry["pointer"]
    fun = functools.partial(pointer, *args, **kwargs)
    future = _memory.event_loop.run_in_executor(_memory.executor, fun, request_id, identity, call_type)
    if return_future:
        return future
    try:
        return_val = await future
        await _memory.server.send_return(identity, request_id, return_val)
    except Exception as e:
        core_log.exception(f"Exception occurred during local execution of function \"{name}\"")
        if call_type == 3:
            await _memory.server.send_exception(identity, request_id, e)


def _run_job(fun, sender):
    ret = None
    try:
        ret = fun()
    except Exception as e:
        print(e)
    if ret:
        return ret


def execute_function(name, *args, **kwargs):
    if not _memory.plugin_system_active:
        raise Exception("Plugin system not initialized")
    if _memory.mode & PluginModeFlags.LOCAL:
        execute_local(name, *args, **kwargs)


class FunctionNotFoundException(Exception):
    def __init__(self, function_name, message="Function not found"):
        self.function_name = function_name
        self.message = f"{message}: {function_name}"
        super().__init__(self.message)


from .networking import PluginClient, PluginServer
