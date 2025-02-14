import pickle
import threading, asyncio
from . import decorators
from .internal.executor import init_plugin_system, execute as async_execute, execute_code as async_execute_code
from .data_structures.enums import PluginModeFlags
from .internal.networking import create_and_start_plugin_server, create_and_start_plugin_client
from .internal.memory import _memory, get_function_entry
from .internal.utils import supervise_future
from .internal import api as _api
from .data_structures import variables
from rixaplugin import settings

get_state_info = _memory.__str__
get_plugin_info = _memory.pretty_print_plugin
get_functions_info = _memory.get_functions

worker_context = threading.local()


def set_tags(plugin_name, tags):
    _memory.apply_tags_plugin(plugin_name, tags)


async def _execute_and_await(function_name, plugin_name, args, kwargs, api_obj, timeout):
    """
    Helper function for synchronous execution of functions in the plugin system.
    Use async_execute for proper async execution.
    """
    future = async_execute(function_name, plugin_name, api_obj=api_obj, args=args, kwargs=kwargs, timeout=timeout,
                           return_future=True)
    # This is somewhat puzzling. The result is only returned when awaited twice.
    # The problem is: I have no clue why
    ret_val = await future
    ret_val = await ret_val
    return ret_val


async def _execute_code_and_await(code, api_obj, timeout):
    """
    Helper function for synchronous execution of code in the plugin system.
    Use async_execute for proper async execution.
    """
    future = async_execute_code(code, api_obj=api_obj, timeout=timeout, return_future=True)
    # This is somewhat puzzling. The result is only returned when awaited twice.
    # The problem is: I have no clue why
    ret_val = await future
    ret_val = await ret_val
    return ret_val


def execute(function_name, plugin_name=None, args=None, kwargs=None, timeout=30):
    """
    Execute a function in the plugin system synchronously i.e. wait for the result.

    :param function_name:
    :param plugin_name:
    :param args:
    :param kwargs:
    :param timeout: Timeout in s before a TimeoutError is raised
    :return:
    """
    api_obj = _api.get_api()
    procmode = _api._mode.get()
    if procmode == 2:
        process_socket = _api._socket.get()
        msg = [_api._req_id.get(), "EXECUTE_FUNCTION", function_name, plugin_name, args, kwargs, timeout]
        parsed = pickle.dumps(msg)
        process_socket.send(parsed)
        ret = pickle.loads(process_socket.recv())
        return ret
    else:
        cur_thread_id = threading.get_ident()
        if cur_thread_id == _memory.main_thread_id:
            raise Exception("Cannot execute plugin code synchronously in main thread! Use async_execute instead.")
        future = asyncio.run_coroutine_threadsafe(
            _execute_and_await(function_name, plugin_name, args=args, kwargs=kwargs, api_obj=api_obj,
                               timeout=timeout), _memory.event_loop)
    return future.result()


def execute_code(code, timeout=30):
    api_obj = _api.get_api()
    procmode = _api._mode.get()
    if procmode == 1:
        future = asyncio.run_coroutine_threadsafe(
            _execute_code_and_await(code, api_obj=api_obj, timeout=timeout), _memory.event_loop)
        return future.result()
    else:
        process_socket = _api._socket.get()
        api_in_ctx = _api._plugin_ctx.get()
        msg = [_api._req_id.get(), "EXECUTE_CODE", code, timeout, api_in_ctx.state, api_in_ctx.plugin_variables]
        parsed = pickle.dumps(msg)
        process_socket.send(parsed)
        ret = process_socket.recv()
        ret, state, plugin_variables = pickle.loads(ret)
        api_in_ctx.state = state
        api_in_ctx.plugin_variables = plugin_variables

        return ret
