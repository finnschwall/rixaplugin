import abc
import asyncio
import atexit
import concurrent
import pickle
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
import zmq

import rixaplugin.rixalogger
from .enums import FunctionPointerType
from .memory import _memory, get_function_entry
import functools
from enum import Flag, auto
from .utils import *
import logging
from .rixa_exceptions import *
from . import api, utils
from .pylot import python_parsing, proxy_builder
import ast

core_log = logging.getLogger("plugin_core")


class PluginModeFlags(Flag):
    LOCAL = auto()
    THREAD = auto()
    PROCESS = auto()
    IPC_SOCKET = auto()
    NETWORK = auto()
    CLIENT = auto()
    SERVER = auto()
    JUPYTER = auto()


PMF_DebugLocal = PluginModeFlags.LOCAL | PluginModeFlags.THREAD
PMF_Server = PluginModeFlags.SERVER | PluginModeFlags.NETWORK | PluginModeFlags.THREAD





async def _start_process_server():
    executor = _memory.executor
    socket = _memory.zmq_context.socket(zmq.ROUTER)
    socket.bind(f"ipc:///tmp/worker_{_memory.ID}.ipc")
    while True:
        identity, message = await socket.recv_multipart()
        message = pickle.loads(message)
        if "ABORT" in message:
            core_log.error("Worker requested shutdown. Shutting down immediately.")
            _memory.clean()
        proc_api = executor.get_api(message[0])
        api_callable = getattr(proc_api, message[1])
        if proc_api.is_remote:
            await api_callable(message[2], message[3])
        else:
            await api_callable(*message[2], **message[3])


def init_plugin_system(mode=PMF_DebugLocal, num_workers=2, debug=False, max_jupyter_messages=10):
    if debug:
        asyncio.get_event_loop().set_debug(True)
        core_log.setLevel(logging.DEBUG)
    test_future= None
    _memory.event_loop = asyncio.get_event_loop()
    if mode & PluginModeFlags.THREAD:
        _memory.executor = CountingThreadPoolExecutor(max_workers=num_workers, initializer=api._init_thread_worker)
        test_future = _memory.executor.submit(api._test_job)

    if mode & PluginModeFlags.PROCESS:
        fut = asyncio.create_task(_start_process_server())
        _memory.executor = CountingProcessPoolExecutor(max_workers=num_workers, initializer=api._init_process_worker,
                                                       initargs=(_memory.ID,))
        fake_api = api.BaseAPI(0, 0)
        test_future = _memory.executor.submit(api._test_job, fake_api)

    if mode & PluginModeFlags.LOCAL:
        pass
    if mode & PluginModeFlags.JUPYTER:
        from .rixalogger import JupyterLoggingHandler
        jupyter_handler = JupyterLoggingHandler(max_jupyter_messages)

        # loggers = [logging.getLogger(name) for name in logging.root.manager.loggerDict]
        # for logger in loggers:
        #     if isinstance(logger, RIXALogger):
        #         logger.addHandler(jupyter_handler)
        root_logger = logging.getLogger()
        if type(root_logger.handlers[0]) == logging.StreamHandler:
            root_logger.removeHandler(root_logger.handlers[0])
        root_logger.addHandler(jupyter_handler)
        core_log.info("Jupyter logging enabled")
    if test_future:
        ret = test_future.result()
    _memory.mode = mode
    _memory.plugin_system_active = True

    api.construct_api_module()
    atexit.register(_memory.clean)
    core_log.debug("Plugin system initialized")


async def execute_networked(func_name, plugin_name, args, kwargs, oneway, request_id,
                            identity, network_adapter):
    plugin_entry = get_function_entry(func_name, plugin_name)
    api_obj = api.RemoteAPI(request_id, identity, network_adapter)

    fut = await _execute(plugin_entry, args, kwargs, api_obj, return_future=True)

    try:
        return_val = await fut
        if not oneway:
            await network_adapter.send_return(identity, request_id, return_val)
    except Exception as e:
        # print(rixaplugin.rixalogger.format_exception(e, without_color=True))
        await network_adapter.send_exception(identity, request_id, e)

    # pointer = plugin_entry["pointer"]
    #
    # fun = functools.partial(pointer, *args, **kwargs)
    # future = _memory.event_loop.run_in_executor(_memory.executor, fun)
    # remote_origin = plugin_entry["remote_origin"]
    # remote_identity = plugin_entry["remote_id"]
    # try:
    #     return_val = await future
    #     await remote_origin.send_return(remote_identity, request_id, return_val)
    # except Exception as e:
    #     core_log.exception(f"Error during execution. ID: {request_id}")
    #     await remote_origin.send_exception(remote_identity, request_id, e)


async def _execute_code(ast_obj, api_obj):
    async def _code_visitor_callback(entry, args, kwargs):
        fut = await _execute(entry, args, kwargs, api_obj, return_future=True, return_time_estimate=False)
        return await fut

    visitor = python_parsing.CodeVisitor(_code_visitor_callback, _memory.function_list)
    await visitor.visit(ast_obj)
    if "__call_res__" in visitor.variables:
        ret_val = visitor.variables["__call_res__"]
    else:
        ret_val = "NO RETURN VALUE"
    if not visitor.least_one_call:
        raise NoEffectException()
    return ret_val


async def execute_code(code, api_obj=None, return_future=True):
    """Execute (a string) as code in the plugin system.

    This is not meant for normal programming, as functionality is severely limited.
    It can be used to provide a safe interface to the plugin functions e.g. in a web interface.
    """
    if not _memory.plugin_system_active:
        raise Exception("Plugin system not initialized")

    if api_obj is None:
        api_obj = api.BaseAPI(0, 0)

    ast_obj = ast.parse(code)

    future = asyncio.create_task(_execute_code(ast_obj, api_obj))

    if return_future:
        return future
    else:
        await supervise_future(future)


async def execute_sync(entry, args, kwargs, api_obj, return_future):
    """
    Runs a local sync function in the plugin system.

    For sync-sync calls, do not use this function, but rather call the function directly.
    :param plugin_entry:
    :param args:
    :param kwargs:
    :param return_future:
    :return:
    """
    if _memory.max_queue < _memory.executor.get_queued_task_count():
        raise QueueOverflowException(f"{entry['plugin_name']} has no available workers.")
    if not _memory.executor and _memory.plugin_system_active:
        raise Exception("Plugin system is wrongly initialized. There is no executor."
                        "Did you forget to set the mode (THREAD/PLUGIN)?")
    if _memory.mode & PluginModeFlags.THREAD:
        fun = functools.partial(api._call_function_sync, entry["pointer"], api_obj, args, kwargs)
    else:
        fun = functools.partial(api._call_function_sync_process, entry["name"], entry["plugin_name"], api_obj.request_id,
                                args, kwargs)
    future = _memory.event_loop.run_in_executor(_memory.executor,
                                                fun, api_obj)  # _memory.executor.submit(pointer, *args, **kwargs)
    if return_future:
        return future
    else:
        await supervise_future(future)


async def execute_async(entry, args, kwargs, api_obj, return_future):
    fut = asyncio.create_task(api._call_function_async(entry["pointer"], api_obj, args, kwargs))
    if return_future:
        return fut
    else:
        await supervise_future(fut)

async def _wait_for_return(future, timeout):
    try:
        return asyncio.wait_for(future, timeout)
    except asyncio.TimeoutError:
        raise RemoteTimeoutException(f"Remote function call timed out after {timeout} seconds.")

async def _execute(plugin_entry, args=(), kwargs={}, api_obj=None, return_future=False, return_time_estimate=False,
                   timeout=10):
    if not api_obj:
        api_obj = api.BaseAPI(0, 0)
    if plugin_entry["type"] & FunctionPointerType.LOCAL:
        if plugin_entry["type"] & FunctionPointerType.SYNC:
            return await execute_sync(plugin_entry, args, kwargs, api_obj, return_future=return_future)
        else:
            return await execute_async(plugin_entry, args, kwargs, api_obj, return_future=return_future)
    elif plugin_entry["type"] & FunctionPointerType.REMOTE:

        if not _memory.plugins[plugin_entry["plugin_name"]]["is_alive"]:
            raise Exception(f"{plugin_entry['plugin_name']} is currently unreachable.")
        _memory.plugins[plugin_entry["plugin_name"]]["active_tasks"] += 1

        fut, est = await plugin_entry["remote_origin"].call_remote_function(plugin_entry, api_obj, args, kwargs, not return_future,
                                                                        return_time_estimate=True)
        if return_time_estimate:
            return await _wait_for_return(fut, 3), est
        else:
            return await _wait_for_return(fut, timeout)


    raise NotImplementedError()


async def execute(function_name, plugin_name=None, args=(), kwargs={}, api_obj=None, return_future=False,
                  return_time_estimate=False, timeout=10):
    if not _memory.plugin_system_active:
        raise Exception("Plugin system not initialized")
    if not api_obj:
        req_id = utils.identifier_from_signature(function_name, args, kwargs)
        api_obj = api.BaseAPI(req_id, _memory.ID)
    plugin_entry = get_function_entry(function_name, plugin_name)
    utils.is_valid_call(plugin_entry, args, kwargs)
    return await _execute(plugin_entry, args, kwargs, api_obj, return_future=return_future,
                          return_time_estimate=return_time_estimate, timeout=timeout)
    # if plugin_entry["type"] & FunctionPointerType.LOCAL:
    #     if plugin_entry["type"] & FunctionPointerType.SYNC:
    #         return await execute_sync(plugin_entry, args, kwargs, api_obj, return_future=return_future)
    #     else:
    #         return await execute_async(plugin_entry, args, kwargs, api_obj, return_future=return_future)
    # raise NotImplementedError()



class CountingThreadPoolExecutor(concurrent.futures.ThreadPoolExecutor):
    def __init__(self, max_workers=None, *args, **kwargs):
        super().__init__(max_workers, *args, **kwargs)
        self._active_tasks = set()
        self.max_task_count = max_workers

    def submit(self, fn, *args, **kwargs):
        future = super().submit(fn)
        self._active_tasks.add(future)
        future.add_done_callback(self._task_completed)
        return future

    def get_max_task_count(self):
        return self._max_workers

    def debug_print(self):
        for num, item in enumerate(self._work_queue.queue):
            print('{}\t{}\t{}\t{}'.format(
                num + 1, item.fn, item.args, item.kwargs,
            ))

    def _task_completed(self, future):
        self._active_tasks.remove(future)

    def get_queued_task_count(self):
        return self._work_queue.qsize()

    def get_active_task_count(self):
        return len(self._active_tasks)

    def get_free_worker_count(self):
        return self._max_workers - len(self._active_tasks)


class CountingProcessPoolExecutor(concurrent.futures.ProcessPoolExecutor):
    def __init__(self, max_workers=None, *args, **kwargs):
        super().__init__(max_workers=max_workers, *args, **kwargs)
        self._active_tasks = 0
        self.max_task_count = max_workers
        self.apis = {}

    def submit(self, fn, *args, **kwargs):
        proc_api = args[0]
        self.apis[proc_api.request_id] = proc_api
        future = super().submit(fn)
        self._active_tasks += 1
        future.add_done_callback(self._task_completed)
        future.request_id = proc_api.request_id
        return future

    def debug_print(self):
        for num, item in enumerate(self._pending_work_items):
            print('{}\t{}\t{}\t{}'.format(
                num + 1, item.fn, item.args, item.kwargs,
            ))

    def get_max_task_count(self):
        return self._max_workers

    def _task_completed(self, future):
        self._active_tasks -= 1
        asyncio.run_coroutine_threadsafe(self.remove_api(future.request_id), _memory.event_loop)

    async def remove_api(self, request_id):
        await asyncio.sleep(1)
        try:
            del self.apis[request_id]
        except:
            raise Exception("INCONSISTENT STATE! Shut down ASAP!")

    def get_api(self, request_id):
        return self.apis[request_id]

    def get_queued_task_count(self):
        return len(self._pending_work_items)

    def get_active_task_count(self):
        return self._active_tasks

    def get_free_worker_count(self):
        return self._max_workers - self._active_tasks


# async def execute(plugin_entry, args, kwargs, return_future=False):
#     if not _memory.plugin_system_active:
#         raise Exception("Plugin system not initialized")
#     if plugin_entry["type"] & FunctionPointerType.LOCAL:
#         if plugin_entry["type"] & FunctionPointerType.SYNC:
#             return await execute_sync(plugin_entry["pointer"], args, kwargs, return_future=return_future)
#         else:
#             pass
#     elif plugin_entry["type"] & FunctionPointerType.REMOTE:
#         if plugin_entry["type"] & FunctionPointerType.CLIENT:
#             return await _memory.server.call_remote_function(plugin_entry, args=args, kwargs=kwargs, one_way=return_future,
#                                    return_time_estimate=True)
#         elif plugin_entry["type"] & FunctionPointerType.SERVER:
#             return await _memory.server.execute_remote(entry["remote_id"], entry["name"], args, kwargs, request_id, return_future=return_future)
#     else:
#         raise Exception("Oh no!")




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
