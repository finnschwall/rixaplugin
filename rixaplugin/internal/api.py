"""
https://www.youtube.com/watch?v=siwpn14IE7E
"""
import contextvars
import functools
import os.path

import zmq

from rixaplugin.internal.memory import _memory, get_function_entry
from rixaplugin.pylot import python_parsing, proxy_builder
import asyncio
import pickle
import logging
import rixaplugin.settings as settings
api_logger = logging.getLogger("rixa.api_internal")



def construct_api_module():
    api_funcs = python_parsing.class_to_func_signatures(BaseAPI)
    # remove self args from all functions
    for i in api_funcs:
        for j in i["args"]:
            if j["name"] == "self":
                i["args"].remove(j)

    def factory_sync(name, args, kwargs):
        api_obj = _plugin_ctx.get()
        try:
            #
            req_id = _req_id.get()
            if _plugin_id:
                if name == "__get_global_ctx__":
                    raise Exception("NOT IMPLEMENTED")
                    return
                try:
                    parsed = pickle.dumps([req_id, "API_FUNCTION", name, args, kwargs])
                except Exception as e:
                    raise e
                _socket.get().send(parsed)
            else:
                api_callable = getattr(api_obj, name)
                if api_obj.is_remote:
                    future = asyncio.run_coroutine_threadsafe(api_callable(args, kwargs), _memory.event_loop)
                else:
                    future = asyncio.run_coroutine_threadsafe(api_callable(*args, **kwargs), _memory.event_loop)
                return_val = future.result()
                return return_val
        except AttributeError:
            raise AttributeError(f"API function {args[0]} not found")

    async def factory_async(name, args, kwargs):
        api_obj = _plugin_ctx.get()
        try:
            api_callable = getattr(api_obj, name)
            await api_callable(*args, **kwargs)
        except AttributeError:
            raise AttributeError(f"API function {args[0]} not found")

    import rixaplugin.sync_api as sync_api
    import rixaplugin.async_api as async_api

    sync_api_module = proxy_builder.create_module("sync_api", api_funcs, description="Synchronous API",
                                                  function_factory=factory_sync, module=sync_api)

    async_sync_api_module = proxy_builder.create_module("async_api", api_funcs, description=None,
                                                        function_factory=factory_async, module=async_api)

    # sys.modules["sync_api"] = sync_api_module


class BaseAPI:
    """
    Base class for all API objs. Simultaneously fallback for calls where no API was passed.

    API objs only exist asynchronously. Sync calls will be wrapped.
    The API implementation is provided by a server on which the plugin system runs.
    It's primary function is to access webserver functionality. For development and consistency reasons,
    serverless API exists as well. This is the base and fallback for all API calls.
    It serves API calls with minimal compatibility, i.e. it just prints the result.

    The API implementation assumes a django server, although as mentioned it is not a requirement.
    """

    @staticmethod
    def get_request_id(function_name, args, kwargs):
        return utils.identifier_from_signature(function_name, args, kwargs)
    @property
    def worker_ctx(self):
        return _context.get()

    def __init__(self, request_id, identity, scope=None):
        self.request_id = request_id
        self.identity = identity
        self.is_remote = False
        self.plugin_variables = {}
        if scope:
            self.scope = scope
        else:
            self.scope = {}

    async def display(self, html=None, json=None, plotly=None, text=None):
        # base implementation works in maximum compatibility mode i.e. just prints
        if html:
            # import traceback
            # import inspect
            # traceback.print_stack()
            #
            # # Get the current frame
            # current_frame = inspect.currentframe()
            #
            # # Get the caller's frame (one level up)
            # caller_frame = current_frame.f_back
            #
            # # Get information about the caller
            # caller_info = inspect.getframeinfo(caller_frame)
            #
            # # Get the class that the method is being called on
            # try:
            #     # Try to get the class of the instance (self)
            #     instance = caller_frame.f_locals['self']
            #     class_name = instance.__class__.__name__
            # except KeyError:
            #     # If 'self' is not found, it might be a static method or a function
            #     class_name = "Not in a class method"
            #
            # print(f"\nCaller Information:")
            # print(f"Class: {class_name}")
            # print(f"File: {caller_info.filename}")
            # print(f"Function: {caller_info.function}")
            # print(f"Line: {caller_info.lineno}")
            print("BASE HTML : ", html[:100])
        if json:
            print("BASE JSON : ", json[:100])
        if plotly:
            print("BASE Plotly was passed")
        if text:
            print("BASE Text : ", text)


    async def display_in_chat(self, tracker_entry = None, text = None, html = None, plotly_obj = None,
            role = None, citations = None, index = None, flags = None):
        # base implementation works in maximum compatibility mode i.e. just prints
        if html:
            print("BASE-CHAT HTML : ", html[:100])
        if plotly_obj:
            print("BASE-CHAT Plotly was passed")
        if text:
            print("BASE-CHAT Text : ", text)

    async def datalog_to_tmp(self, message, write_mode = "a"):
        """
        Write into a file in the tmp directory.

        Filename is the request_id of the API object.
        Folder can be specified via settings.TMP_DATA_LOG_FOLDER
        This is not meant for normal logging, but for large text dumps (e.g. a chat history) that are tied to a specific
        request.
        :param message: String to write
        :param write_mode: Mode to open the file in. Default is append.
        """
        with open(os.path.join(settings.TMP_DATA_LOG_FOLDER, f"{self.request_id}.log"), write_mode) as f:
            f.write(message)


    async def execute_code_on_remote(self, code):
        fut = await executor.execute_code(code, api_obj=self, return_future=True)
        ret = await fut
        return ret

    async def save_usr_obj(self, key, value, sync_db=False):
        global __fake_usr_data
        """
        Store user specific persistent data. 
        :param key: 
        :param value: 
        :param sync_db: Immediately write to the server database
        """
        __fake_usr_data[key] = value

    async def retrieve_usr_obj(self, key):
        global __fake_usr_data
        """
        Retrieve user specific persistent data.
        :param key: 
        :return: 
        """
        return __fake_usr_data.get(key, None)

    async def sync_session_storage_db(self):
        """
        Sync the session storage with the database. Use sparingly!
        """
        pass

    async def call_client_js(self, function_name, *args, oneway=True):
        """
        Call a JS function in the clients browser

        :param function_name: JS function name
        :param args: Arguments to pass to the function
        :param oneway: If True, the call will be one way, i.e. no return value will be expected
        :return: return value of the JS function
        """
        pass

    async def show_message(self, message, message_type="info"):
        """
        Display a message to the user.

        Will show a box that needs to be acknowledged before the website can be used again.
        There is always just one message box, so if a new message is shown, the old one will be replaced.
        :param message: Message to display
        :param message_type:
        """
        print(f"{message_type.upper()}: {message}")

    async def call(self, function_name, args_func, kwargs_func, **kwargs):
        """
        Low level remote call.

        Used for more fine grained control over the call. If you don't know what this is, you probably don't need it.
        :param function_name:
        :param args_func:
        :param kwargs_func:
        :param kwargs:
        :return:
        """
        pass


class RemoteAPI(BaseAPI):
    """
    API class for remote calls.

    Relays all calls to client for execution. Only exception is logging, which will be both logged locally and sent to
    the server.
    """

    def __init__(self, request_id, identity, network_adapter, scope=None):
        self.request_id = request_id
        self.identity = identity
        self.is_remote = True
        self.network_adapter = network_adapter
        if scope:
            self.scope = scope
        else:
            self.scope = {}

    def __getattribute__(self, item):
        attr = super().__getattribute__(item)
        if callable(attr) and hasattr(BaseAPI, item) and not item.startswith("__") and item not in ["datalog_to_tmp"]:
            return functools.partial(self.network_adapter.send_api_call, self.identity, self.request_id, item)
        else:
            return attr


class JupyterAPI(BaseAPI):
    """
    API class for Jupyter Notebooks.

    Does the same as the base API, but uses jupyters display methods when possible.
    Strongly recommended for development and testing.
    """

    def __init__(self, request_id, identity):
        super().__init__(request_id, identity)
        from IPython.display import display, HTML
        self.display = display
        self.HTML = HTML

    async def display(self, html=None, json=None, plotly=None, text=None):
        # here jupyterlab abilities are utilized
        if html:
            self.display(self.HTML(html))
        if json:
            self.display(self.HTML(f"<code>{json}</code>"))
        if plotly:
            plotly.show()
        if text:
            print("DISPLAY", text)

    async def show_message(self, message, message_type="info"):
        self.display(self.HTML(f"<div class=\"alert alert-{message_type}\" role=\"alert\">{message}</div>"))


def _is_api_present():
    return _plugin_ctx.get() is not None


def _test_job():
    return 5


def _init_thread_worker():
    global _mode
    _mode.set(1)
    for func in _memory.worker_init:
        func()


def _init_process_worker(plugin_id):
    global _zmq_context, _socket, _plugin_id, _mode
    # worker_ctx = _context.get()
    for func in _memory.worker_init:
        func()
    _zmq_context = zmq.Context()
    socket = _zmq_context.socket(zmq.DEALER)
    _socket.set(socket)
    socket.connect(f"ipc:///tmp/worker_{plugin_id}.ipc")
    _plugin_id = plugin_id
    _mode.set(2)


def get_api():
    return _plugin_ctx.get()


def _call_function_sync_process(name, plugin_name, req_id, args, kwargs, ):
    global _req_id
    _req_id.set(req_id)
    func = get_function_entry(name, plugin_name)["pointer"]
    return_val = func(*args, **kwargs)
    return return_val


def _call_function_sync(func, api_obj, args, kwargs, ):
    _plugin_ctx.set(api_obj)
    return_val = func(*args, **kwargs)
    return return_val


async def _call_function_async(func, api_obj, args, kwargs, return_future=True):
    _plugin_ctx.set(api_obj)
    return await func(*args, **kwargs)


def relay_module(*args, **kwargs):
    global _mode
    print("RELAY", _mode.get(), args, kwargs)


_plugin_ctx = contextvars.ContextVar('__plugin_api', default=BaseAPI(-1, -1))
__fake_usr_data = {}
_zmq_context = None
_context = contextvars.ContextVar('_context', default={})
_plugin_id = None
_req_id = contextvars.ContextVar('_req_id', default=None)
_identity = contextvars.ContextVar('_identity', default=None)
_socket = contextvars.ContextVar('_socket', default=None)
_mode = contextvars.ContextVar('_mode', default=0)
_variables = contextvars.ContextVar('_variables', default={})

from rixaplugin.internal import executor, utils

