"""
https://www.youtube.com/watch?v=siwpn14IE7E
"""
import contextvars
import functools

import zmq

from rixaplugin.internal.memory import _memory, get_function_entry
from rixaplugin.pylot import python_parsing, proxy_builder
import asyncio
import pickle
import logging

api_logger = logging.getLogger("API_INTERNAL")


# usually all plugin functions are run not directly but through the plugin system i.e. an executor
# plugin function calls outside the plugin system are possible, however API calls have different meaning
# using e.g. a display method locally should immediately display the result, while using it through the plugin system
# should result in a oneway call to display on the remote
# class ContextObject:
#     # def __init__(self):
#     #     # Internal dictionary to store attributes
#
#     def __get_ctx__(self):
#         return _context.get()
#
#     def __getattr__(self, name):
#         # Return the value if it exists, otherwise return None
#         return self.__get_ctx__().get(name, None)
#
#     def __setattr__(self, name, value):
#         # Set the attribute in the internal dictionary
#         self.__get_ctx__()[name] = value
#
#     def __dir__(self):
#         # List all attached variables/objects
#         return self.__get_ctx__().keys()
#
#
# worker_context = ContextObject()


# fake user persistent data to allow for consistent behavior and testing without server

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
                    parsed = pickle.dumps([req_id, name, args, kwargs])
                except Exception as e:
                    raise e
                _socket.get().send(parsed)

            else:
                api_callable = getattr(api_obj, name)
                return asyncio.run_coroutine_threadsafe(api_callable(args, kwargs), _memory.event_loop)
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

    @property
    def worker_ctx(self):
        return _context.get()

    def __init__(self, request_id, identity):
        self.request_id = request_id
        self.identity = identity
        self.is_remote = False

    async def display(self, html=None, json=None, plotly=None, text=None):
        # base implementation works in maximum compatibility mode i.e. just prints
        if html:
            print("HTML : ", html)
        if json:
            print("JSON : ", json)
        if plotly:
            print("Plotly was passed")
        if text:
            print("Text : ", text)

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


# class PublicSyncApi(BaseAPI):
#     """
#     API class for public sync calls.
#
#     Abstracts away the retrieval of the actual API obj stored in the context.
#     """
#
#     @staticmethod
#     def get_call_api():
#         global _plugin_ctx
#         return _plugin_ctx.get()
#
#     def __getattribute__(self, item):
#         print(item)
#         attr = super().__getattribute__(item)
#         if callable(attr) and hasattr(BaseAPI, item) and not item.startswith("__"):
#             api = PublicSyncApi.get_call_api()
#             actual_api_method = getattr(api, item)
#             return actual_api_method
#         else:
#             return attr


class RemoteAPI(BaseAPI):
    """
    API class for remote calls.

    Relays all calls to client for execution. Only exception is logging, which will be both logged locally and sent to
    the server.
    """

    def __init__(self, request_id, identity, network_adapter):
        self.request_id = request_id
        self.identity = identity
        self.is_remote = True
        self.network_adapter = network_adapter

    # async def __call_remote__(self, name, args, kwargs):
    #     print("NETWORK", self.network_adapter)
    #     await self.network_adapter.send_api_call(self.request_id, self.identity, name, args, kwargs)

    def __getattribute__(self, item):
        attr = super().__getattribute__(item)
        if callable(attr) and hasattr(BaseAPI, item) and not item.startswith("__"):
            return functools.partial(self.network_adapter.send_api_call, self.identity, self.request_id, item)
        else:
            return attr


# class ProcessAPI(BaseAPI):
#     """
#     API class for spawned processes.
#
#     Relays all calls to main process.
#     """
#
#     def __init__(self, request_id, identity):
#         self.request_id = request_id
#         self.identity = identity
#
#     def __get_global_ctx__(self):
#         print("hey")
#
#     def __getattribute__(self, item):
#         global _socket
#         attr = super().__getattribute__(item)
#         print("Close enough?")
#         if item == "__get_global_ctx__":
#             return self.__get_global_ctx__()
#         if callable(attr) and hasattr(BaseAPI, item) and not item.startswith("__"):
#             print("ITEM", item)
#             try:
#                 parsed = pickle.dumps(item)
#             except Exception as e:
#                 print("?")
#                 raise e
#             print("??")
#             _socket.send(parsed)
#             print("???")
#         else:
#             return attr
# self.network_adapter.send_api_call(self.request_id, self.identity, item)


class JupyterAPI(BaseAPI):
    """
    API class for Jupyter Notebooks.

    Does the same as the base API, but uses jupyters display methods when possible.
    Strongly recommended for development and testing.
    """

    def __init__(self):

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
            print(text)

    async def show_message(self, message, message_type="info"):
        self.display(self.HTML(f"<div class=\"alert alert-{message_type}\" role=\"alert\">{message}</div>"))


def _is_api_present():
    return _plugin_ctx.get() is not None


def _test_job():
    return 5


def _init_thread_worker():
    for func in _memory.worker_init:
        func()


def _init_process_worker(plugin_id):
    global _zmq_context, _socket, _plugin_id
    # worker_ctx = _context.get()
    for func in _memory.worker_init:
        func()
    _zmq_context = zmq.Context()
    socket = _zmq_context.socket(zmq.DEALER)
    _socket.set(socket)
    socket.connect(f"ipc:///tmp/worker_{plugin_id}.ipc")
    _plugin_id = plugin_id

    #     try:
    #
    #     except Exception as e:
    #         api_logger.exception("Worker init function failed. Plugin will not be loaded")
    #         abort_message = {"ABORT":"ABORT"}
    #         socket.send(pickle.dumps(abort_message))


def _call_function_sync_process(name, plugin_name, req_id, args, kwargs, ):
    global _req_id
    _req_id.set(req_id)
    # _identity.set(identity)
    # api_obj = ProcessAPI(req_id, identity)
    # _plugin_ctx.set(api_obj)
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


_plugin_ctx = contextvars.ContextVar('__plugin_api', default=BaseAPI(0, 0))
__fake_usr_data = {}
_zmq_context = None
_context = contextvars.ContextVar('_context', default={})
# _socket = None
_plugin_id = None
_req_id = contextvars.ContextVar('_req_id', default=None)
_identity = contextvars.ContextVar('_identity', default=None)
_socket = contextvars.ContextVar('_socket', default=None)

# def _call_function_async(func, args, kwargs, api_obj=None, return_future = True):


# set ctx vars for API
# def _call_function(func, args, kwargs, request_id, identity, callstack_type : CallstackType):
#     call_api = BaseAPI(request_id, identity)
#     # if callstack_type & CallstackType.LOCAL:
#     #     if callstack_type & CallstackType.ASYNCIO:
#
#     _plugin_ctx.set(call_api)
#
#     return _plugin_ctx.run(func, *args, **kwargs)