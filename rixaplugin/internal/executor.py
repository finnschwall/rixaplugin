import asyncio
import atexit
import concurrent
import pickle
import time
import types
from concurrent.futures import ThreadPoolExecutor
import zmq

from rixaplugin.data_structures.enums import PluginModeFlags, FunctionPointerType
from rixaplugin.internal.memory import _memory, get_function_entry
import functools
from enum import Flag, auto
from rixaplugin.internal.utils import *
import logging
from rixaplugin.data_structures.rixa_exceptions import *
from rixaplugin.internal import api, utils
from rixaplugin.pylot import python_parsing
import ast

core_log = logging.getLogger("rixa.core")

PMF_DebugLocal = PluginModeFlags.LOCAL | PluginModeFlags.THREAD
PMF_Server = PluginModeFlags.SERVER | PluginModeFlags.NETWORK | PluginModeFlags.THREAD


async def _start_process_server(socket):
    executor = _memory.executor
    while True:
        identity, message = await socket.recv_multipart()
        message = pickle.loads(message)
        if "ABORT" in message:
            core_log.error("Worker requested shutdown. Shutting down immediately.")
            _memory.clean()
        # if message[0] == "EXECUTE_FUNCTION":
        proc_api = executor.get_api(message[0])
        if message[1] == "EXECUTE_FUNCTION":
            future = await execute(message[2], message[3], message[4], message[5], proc_api, True, message[6])
            future.add_done_callback(lambda fut: socket.send_multipart([identity, pickle.dumps(fut.result())]))
        if message[1] == "API_FUNCTION":
            api_callable = getattr(proc_api, message[2])
            if proc_api.is_remote:
                await api_callable(message[3], message[4])
            else:
                await api_callable(*message[3], **message[4])


def init_plugin_system(mode=PMF_DebugLocal, num_workers=None, debug=False, max_jupyter_messages=10):
    if _memory.plugin_system_active:
        raise Exception("Plugin system already initialized. You'll need to restart the process to reinitialize.")
    if debug:
        asyncio.get_event_loop().set_debug(True)
        core_log.setLevel(logging.DEBUG)
    if not num_workers:
        num_workers = settings.DEFAULT_MAX_WORKERS
    test_future = None
    _memory.event_loop = asyncio.get_event_loop()
    if mode & PluginModeFlags.THREAD and mode & PluginModeFlags.PROCESS:
        raise Exception("Cannot run in both THREAD and PROCESS mode.")
    api.construct_api_module()
    if mode & PluginModeFlags.THREAD:
        _memory.executor = CountingThreadPoolExecutor(max_workers=num_workers, initializer=api._init_thread_worker)
        test_future = _memory.executor.submit(api._test_job)

    if mode & PluginModeFlags.PROCESS:
        socket = _memory.zmq_context.socket(zmq.ROUTER)
        socket.bind(f"ipc:///tmp/worker_{_memory.ID}.ipc")

        fut = asyncio.create_task(_start_process_server(socket))

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
    if mode & PluginModeFlags.SERVER:
        from rixaplugin.internal.networking import create_and_start_plugin_server
        asyncio.create_task(create_and_start_plugin_server(settings.DEFAULT_PLUGIN_SERVER_PORT,
                                                           use_auth=not settings.USE_AUTH_SYSTEM, return_future=False))

    _memory.mode = mode
    _memory.plugin_system_active = True


    atexit.register(_memory.clean)
    core_log.debug("Plugin system initialized")


async def execute_networked(func_name, plugin_name, args, kwargs, oneway, request_id,
                            identity, network_adapter):
    plugin_entry = get_function_entry(func_name, plugin_name)
    api_obj = api.RemoteAPI(request_id, identity, network_adapter)

    try:
        fut = await _execute(plugin_entry, args, kwargs, api_obj, return_future=True)
    except Exception as e:
        await network_adapter.send_exception(identity, request_id, e)
        return
    try:
        return_val = await fut
        if not oneway:
            await network_adapter.send_return(identity, request_id, return_val)
    except Exception as e:
        await network_adapter.send_exception(identity, request_id, e)


async def _execute_code(ast_obj, api_obj):
    async def _code_visitor_callback(entry, args, kwargs):
        fut = await _execute(entry, args, kwargs, api_obj, return_future=True, return_time_estimate=False)
        return await fut

    visitor = python_parsing.CodeVisitor(_code_visitor_callback, _memory.function_list)

    await visitor.visit(ast_obj)

    # function_missing = None
    # try:
    #     await visitor.visit(ast_obj)
    # except FunctionNotFoundException as f:
    #     function_missing = f.message
    # if function_missing:
    #     exc =  FunctionNotFoundException("")
    #     exc.message = function_missing
    #     raise exc
    if "__call_res__" in visitor.variables:
        ret_val = visitor.variables["__call_res__"]
    else:
        ret_val = "NO RETURN VALUE"
    if not visitor.least_one_call:
        raise NoEffectException()
    return ret_val


async def execute_code(code, api_obj=None, return_future=True, timeout=30):
    """Execute (a string) as code in the plugin system.

    This is not meant for normal programming, as functionality is severely limited.
    It can be used to provide a safe interface to the plugin functions e.g. in a web interface.
    """
    if not _memory.plugin_system_active:
        raise Exception("Plugin system not initialized")

    if api_obj is None:
        api_obj = api.BaseAPI(0, 0)
        # cur_api = api._plugin_ctx.get()
        # if cur_api.request_id == -1 and cur_api.identity==-1:
        #     if _memory.mode & PluginModeFlags.JUPYTER:
        #         api_obj = api.JupyterAPI(0, 0)
        #     else:
        #         api_obj = api.BaseAPI(0, 0)
        # else:
        #     api_obj = cur_api

    ast_obj = ast.parse(code)

    future = asyncio.create_task(_execute_code(ast_obj, api_obj))

    if return_future:
        return future
        # return await _wait_for_return(future, timeout)
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
        fun = functools.partial(api._call_function_sync_process, entry["name"], entry["plugin_name"],
                                api_obj.request_id,
                                args, kwargs)
    future = _memory.event_loop.run_in_executor(_memory.executor,
                                                fun, api_obj)  # _memory.executor.submit(pointer, *args, **kwargs)
    if return_future:
        return future
    else:
        await supervise_future(future)


async def execute_async(entry, args, kwargs, api_obj, return_future):
    fut = asyncio.create_task(api._call_function_async(entry["pointer"], api_obj, args, kwargs))
    _memory.tasks_in_system -= 1
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
                   timeout=30):
    if api_obj is None:
        api_obj = api.BaseAPI(0, 0)
    if return_future:
        # tasks that don't return are tasks too. But it's hard to accurately check if/when they're done.
        _memory.tasks_in_system += 1
    if plugin_entry["type"] & FunctionPointerType.LOCAL:
        if plugin_entry["type"] & FunctionPointerType.SYNC:
            return await execute_sync(plugin_entry, args, kwargs, api_obj, return_future=return_future)
        else:
            return await execute_async(plugin_entry, args, kwargs, api_obj, return_future=return_future)
    elif plugin_entry["type"] & FunctionPointerType.REMOTE:
        if not _memory.plugins[plugin_entry["plugin_name"]]["is_alive"]:
            raise Exception(f"{plugin_entry['plugin_name']} is currently unreachable.")
        _memory.plugins[plugin_entry["plugin_name"]]["active_tasks"] += 1

        fut, est = await plugin_entry["remote_origin"].call_remote_function(plugin_entry, api_obj, args, kwargs,
                                                                            not return_future,
                                                                            return_time_estimate=True)
        if return_time_estimate:
            return fut, est
            # return await _wait_for_return(fut, timeout), est
        else:
            return fut
            # return await _wait_for_return(fut, timeout)

    raise NotImplementedError()


async def execute(function_name, plugin_name=None, args=None, kwargs=None, api_obj=None, return_future=False,
                  return_time_estimate=False, timeout=30):
    """
    Execute a function in the plugin system.

    This function is used to execute a function in the plugin system. It first checks if the plugin system is active,
    then it gets the function entry from the function name and plugin name. It validates the call and then executes the function.

    Args:
        function_name (str): The name of the function to be executed.
        plugin_name (str, optional): The name of the plugin where the function is located. Defaults to None.
        args (tuple, optional): The positional arguments to pass to the function. Defaults to ().
        kwargs (dict, optional): The keyword arguments to pass to the function. Defaults to {}.
        api_obj (BaseAPI, optional): The API object to use for the function call. If None, a new BaseAPI object is created. Defaults to None.
        return_future (bool, optional): If True, the function will return a future of the function call. Defaults to False.
        return_time_estimate (bool, optional): If True, the function will return a time estimate of the function call. Defaults to False.
        timeout (int, optional): The maximum time to wait for the function call to complete. Defaults to 10.

    Raises:
        Exception: If the plugin system is not initialized.

    Returns:
        Future or any: If return_future is True, it returns a Future object. Otherwise, it returns the result of the function call.
    """
    if kwargs is None:
        kwargs = {}
    if args is None:
        args = ()
    if not isinstance(args, tuple):
        if not isinstance(args, list):
            args = [args]
    if not _memory.plugin_system_active:
        raise Exception("Plugin system not initialized")
    if not api_obj:
        req_id = utils.identifier_from_signature(function_name, args, kwargs)
        if _memory.mode & PluginModeFlags.JUPYTER:
            api_obj = api.JupyterAPI(req_id, _memory.ID)
        else:
            api_obj = api.BaseAPI(req_id, _memory.ID)

    plugin_entry = get_function_entry(function_name, plugin_name)
    utils.is_valid_call(plugin_entry, args, kwargs)
    return await _execute(plugin_entry, args, kwargs, api_obj, return_future=return_future,
                          return_time_estimate=return_time_estimate, timeout=timeout)


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
        _memory.tasks_in_system -= 1
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
        _memory.tasks_in_system -= 1
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



def fake_function(func_name, plugin_name, *args, **kwargs):
    print(f"Fake function {func_name} called with {args} and {kwargs}")
    # await execute(func_name, plugin_name, args, kwargs)


# class EmptyModule(types.ModuleType):
#     """
#     A custom module that returns an empty module for any attribute access.
#     """
#     # def __init__(self, name):
#     #     super().__init__(name)
#     #     self._is_empty=True
#     def __getattr__(self, name):
#         print("WTF", name)
#         if name.startswith("__") or name.startswith("_") or not self._is_empty:
#             return super().__getattr__(name)
#         return types.ModuleType(name)

# sys.modules["rixaplugin.remote"] = EmptyModule("rixaplugin.remote")

# def on_remote_plugin_import(name):
#     module = types.ModuleType(name)#EmptyModule(name)
#     module.__file__ = f"{name}.py"
#     module.__doc__ = "Auto-generated module for RPC remote plugin"
#     sys.modules[name] = module
#     return module
#
# def install_import_hook():
#     original_import = __builtins__['__import__']
#     def custom_import(name, globals=None, locals=None, fromlist=(), level=0):
#
#         if name.startswith('remote_'):
#             print(name)
#             module = on_remote_plugin_import(name)
#             _memory.remote_dummy_modules[name] = module
#             return module
#             print("A")
#             if name == "rixaplugin.remote":
#                 return on_remote_plugin_import(name)
#             module = types.ModuleType(name)#on_remote_plugin_import(name)
#
#             return module
#         return original_import(name, globals, locals, fromlist, level)
#     __builtins__['__import__'] = custom_import
#
# install_import_hook()