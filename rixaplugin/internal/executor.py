import asyncio
import atexit
import concurrent
import os
import pickle
import time
import types
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

import zmq

from rixaplugin.data_structures.enums import PluginModeFlags, FunctionPointerType
from rixaplugin.internal.memory import _memory, get_function_entry_by_name, get_function_entry
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


def handle_return_process(fut, socket=None, identity=None, api_obj=None):
    try:
        res = fut.result()
        socket.send_multipart([identity, pickle.dumps([res,api_obj.state, api_obj.plugin_variables])])
    except RemoteException as e:
        socket.send_multipart([identity, pickle.dumps([e,api_obj.state, api_obj.plugin_variables ])])
    except Exception as e:
        socket.send_multipart([identity, pickle.dumps([e,api_obj.state, api_obj.plugin_variables ])])

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
        elif message[1] == "EXECUTE_CODE":
            try:
                future = await execute_code(message[2], proc_api, True, message[3], state=message[4], plugin_variables=message[5])

                #future.add_done_callback(lambda fut: socket.send_multipart([identity, pickle.dumps(fut.result())]))
                future.add_done_callback(lambda fut: handle_return_process(fut, socket, identity, proc_api))
            except Exception as e:
                socket.send_multipart([identity, pickle.dumps(e)])

        elif message[1] == "API_FUNCTION":
            api_callable = getattr(proc_api, message[2])
            if proc_api.is_remote:
                await api_callable(message[3], message[4])
            else:
                await api_callable(*message[3], **message[4])
        else:
            raise Exception("Invalid proc message received on main thread. Process is dead!")


def init_plugin_system(mode=PMF_DebugLocal, num_workers=None, debug=False, max_jupyter_messages=10):
    if _memory.plugin_system_active:
        raise Exception("Plugin system already initialized. You'll need to restart the process to reinitialize.")
    if debug:
        asyncio.get_event_loop().set_debug(True)
        core_log.setLevel(logging.DEBUG)
    if not num_workers:
        num_workers = settings.DEFAULT_MAX_WORKERS

    import_error = False
    if settings.AUTO_IMPORT_PLUGINS:
        for plugin in settings.AUTO_IMPORT_PLUGINS:
            import importlib
            try:
                module = importlib.import_module(plugin)
            except Exception as e:
                import_error = True
                core_log.error(f"Could not import {plugin}. Error: {e}")
                continue
        if not import_error:
            core_log.info("All plugins imported successfully")

    if settings.AUTO_IMPORT_PLUGINS_PATHS:
        raise NotImplementedError()

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
        try:
            socket.bind(f"ipc:///tmp/worker_{_memory.ID}.ipc")
        except Exception as e:
            core_log.critical(f"IPC name not unique! Maybe this program was previously started without proper cleanup? {e}")
            raise e
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
                                                           use_auth=settings.USE_AUTH_SYSTEM, return_future=False))

    if settings.AUTO_CONNECTIONS:
        from rixaplugin.internal.networking import create_and_start_plugin_client
        for conn in settings.AUTO_CONNECTIONS:
            split = conn.split("-")
            if len(split) == 1:
                address, port = split[0].split(":")
                key_name = None
            elif len(split) == 2:
                address, port = split[0].split(":")
                key_name = split[1]
            else:
                raise Exception("Invalid connection string")
            kwargs = {"use_auth":settings.USE_AUTH_SYSTEM, "return_future":False,"client_key_file_name":"server.key_secret",
                      "raise_on_connection_failure":False}
            if key_name:
                kwargs["server_key_file_name"] = key_name + ".key"

            asyncio.create_task(create_and_start_plugin_client(address, port, **kwargs))


    _memory.mode = mode
    _memory.plugin_system_active = True


    # atexit.register(_memory.clean)


    for func in _memory.global_init:
        func()

    if not os.path.exists(settings.TMP_DATA_LOG_FOLDER):
        os.makedirs(settings.TMP_DATA_LOG_FOLDER)

    for i in settings.AUTO_APPLY_TAGS:
        plugin, tag = i.split(":")
        _memory.add_tag_to_plugin(plugin, tag)

    core_log.debug("Plugin system initialized")


async def execute_networked(func_name, plugin_name, plugin_id, args, kwargs, oneway, request_id,
                            identity, network_adapter, scope, plugin_variables=None, state=None):
    plugin_entry = get_function_entry(func_name, plugin_id)

    api_obj = api.RemoteAPI(request_id, identity, network_adapter, scope=scope, plugin_variables=plugin_variables, state=state)
    try:
        fut = await _execute(plugin_entry, args, kwargs, api_obj, return_future=True)

    except Exception as e:
        await network_adapter.send_exception(identity, request_id, e)
        return
    try:
        return_val = await fut
        if not oneway:
            await network_adapter.send_return(identity, request_id, return_val, state=api_obj.state)
    except Exception as e:
        await network_adapter.send_exception(identity, request_id, e)


async def _execute_code(ast_obj, api_obj):

    async def _code_visitor_callback(entry, args, kwargs):
        fut = await _execute(entry, args, kwargs, api_obj, return_future=True, return_time_estimate=False)
        try:
            ret_var = await asyncio.wait_for(fut, timeout=settings.FUNCTION_CALL_TIMEOUT)
            return ret_var
        except asyncio.TimeoutError:
            raise Exception(f"Execution of {entry['name']} in {entry['plugin_name']} timed out after {settings.FUNCTION_CALL_TIMEOUT} "
                            f"seconds. This timeout was detected by the FUNCTION_CALLING system."
                            f"This should not happen and in all likelihood the function is broken. Do not call it again!"
                            f"You will potentially deadlock the system!"
                            f"Failure to comply will lead to ban of user that initiated request.")
        # return await fut
    visitor = python_parsing.CodeVisitor(_code_visitor_callback, _memory.get_functions(api_obj.scope))

    await visitor.visit(ast_obj)

    if "__call_res__" in visitor.variables:
        ret_val = visitor.variables["__call_res__"]
    else:
        ret_val = "NO RETURN VALUE"
    if not visitor.least_one_call:
        raise NoEffectException("Did you miss a function call? Or parentheses? No calls were detected in the code.")
    return ret_val


async def execute_code(code, api_obj=None, return_future=True, timeout=30, scope=None, state=None, plugin_variables=None):
    """Execute (a string) as code in the plugin system.

    This is not meant for normal programming, as functionality is severely limited.
    It can be used to provide a safe interface to the plugin functions e.g. in a web interface.
    """
    if not _memory.plugin_system_active:
        raise Exception("Plugin system not initialized")
    if api_obj is None:
        api_obj = api.BaseAPI(0, 0)
        if scope:
            api_obj.scope = scope
    if state:
        api_obj.state = state
    if plugin_variables:
        api_obj.plugin_variables = plugin_variables

    ast_obj = ast.parse(code)

    future = asyncio.create_task(_execute_code(ast_obj, api_obj))

    if return_future:
        return future
    else:
        await supervise_future(future)


async def _process_api_state(fut, api_obj):
    results = await fut
    state, plugin_variables, return_val = results
    api_obj.state = state
    api_obj.plugin_variables = plugin_variables
    return return_val

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
        fun = functools.partial(api._call_function_sync_process, entry["name"], entry["plugin_id"],
                                api_obj.request_id,
                                args, kwargs, api_obj.state, api_obj.plugin_variables)
    future = _memory.event_loop.run_in_executor(_memory.executor,
                                                fun, api_obj)  # _memory.executor.submit(pointer, *args, **kwargs)
    if return_future:
        if _memory.mode & PluginModeFlags.PROCESS:
            wrapped_future = asyncio.ensure_future(_process_api_state(future, api_obj))
            return wrapped_future
        else:
            return future
        # return future
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
                   timeout=None):
    if api_obj is None:
        api_obj = api.BaseAPI(0, 0)
    if return_future:
        # tasks that don't return are tasks too. But it's hard to accurately check if/when they're done.
        _memory.tasks_in_system += 1
    if not timeout:
        timeout = settings.FUNCTION_CALL_TIMEOUT
    async def execute_with_timeout(coroutine):
        try:
            return await asyncio.wait_for(coroutine, timeout=5)
        except asyncio.TimeoutError:
            raise Exception(f"Execution of {plugin_entry['plugin_name']} timed out after {timeout} seconds.")

    if plugin_entry["type"] & FunctionPointerType.LOCAL:
        if plugin_entry["type"] & FunctionPointerType.SYNC:
            coroutine = execute_sync(plugin_entry, args, kwargs, api_obj, return_future=return_future)
        else:
            coroutine = execute_async(plugin_entry, args, kwargs, api_obj, return_future=return_future)
        if return_future:
            return await coroutine
        return await execute_with_timeout(coroutine)

    elif plugin_entry["type"] & FunctionPointerType.REMOTE:
        if not _memory.plugins[plugin_entry["id"]]["is_alive"]:
            raise RemoteOfflineException(f"{plugin_entry['plugin_name']} is currently unreachable.")
        _memory.plugins[plugin_entry["id"]]["active_tasks"] += 1
        fut, est = await plugin_entry["remote_origin"].call_remote_function(plugin_entry, api_obj, args, kwargs,
                                                                            not return_future,
                                                                            return_time_estimate=True)
        if return_time_estimate:
            if return_future:
                return fut, est
            return await execute_with_timeout(fut), est
        else:
            if return_future:
                return fut
            return await execute_with_timeout(fut)

    # if plugin_entry["type"] & FunctionPointerType.LOCAL:
    #     if plugin_entry["type"] & FunctionPointerType.SYNC:
    #         return await execute_sync(plugin_entry, args, kwargs, api_obj, return_future=return_future)
    #     else:
    #         return await execute_async(plugin_entry, args, kwargs, api_obj, return_future=return_future)
    # elif plugin_entry["type"] & FunctionPointerType.REMOTE:
    #     if not _memory.plugins[plugin_entry["id"]]["is_alive"]:
    #         raise Exception(f"{plugin_entry['plugin_name']} is currently unreachable.")
    #     _memory.plugins[plugin_entry["id"]]["active_tasks"] += 1
    #
    #     fut, est = await plugin_entry["remote_origin"].call_remote_function(plugin_entry, api_obj, args, kwargs,
    #                                                                         not return_future,
    #                                                                         return_time_estimate=True)
    #     if return_time_estimate:
    #         return fut, est
    #         # return await _wait_for_return(fut, timeout), est
    #     else:
    #         return fut
    #         # return await _wait_for_return(fut, timeout)
    #
    # raise NotImplementedError()


async def execute(function_name, plugin_name=None, args=None, kwargs=None, api_obj=None, return_future=False,
                  return_time_estimate=False, timeout=30, scope=None):
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
        scope (dict, optional): Manual scope if no API obj is provided. Will set scope for constructed API object. Defaults to None.

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
        potential_api = api.get_api()
        #check if potential_api is BaseAPI or a derived class. If it is "just" a BaseAPI, create a new API object
        if isinstance(potential_api, api.BaseAPI) and not type(potential_api) == api.BaseAPI:
            api_obj = potential_api

        else:
            req_id = utils.identifier_from_signature(function_name, args, kwargs)
            if _memory.mode & PluginModeFlags.JUPYTER:
                api_obj = api.JupyterAPI(req_id, _memory.ID, scope=scope)
            else:
                api_obj = api.BaseAPI(req_id, _memory.ID, scope=scope)
    plugin_entry = get_function_entry_by_name(function_name, plugin_name)
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
        if settings.LOG_PROCESSPOOL:
            if not os.path.exists(os.path.join(settings.WORKING_DIRECTORY, "log", "processpool.csv")):
                with open(os.path.join(settings.WORKING_DIRECTORY, "log", "processpool.csv"), "w") as f:
                    f.write("time;request_id;is_finished;active_workers;queued_tasks\n")

    def submit(self, fn, *args, **kwargs):
        proc_api = args[0]
        self.apis[proc_api.request_id] = proc_api
        if settings.LOG_PROCESSPOOL:
            with open(os.path.join(settings.WORKING_DIRECTORY, "log", "processpool.csv"), "a") as f:
                f.write(f"{datetime.now().isoformat()};{proc_api.request_id};0;{self._active_tasks};{len(self._pending_work_items)}\n")
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
        if settings.LOG_PROCESSPOOL:
            with open(os.path.join(settings.WORKING_DIRECTORY, "log", "processpool.csv"), "a") as f:
                f.write(f"{datetime.now().isoformat()};{future.request_id};1;{self._active_tasks};{len(self._pending_work_items)}\n")

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

