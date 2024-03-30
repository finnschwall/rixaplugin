from .enums import CallstackType
import contextvars
from .memory import _memory
# usually all plugin functions are run not directly but through the plugin system i.e. an executor
# plugin function calls outside the plugin system are possible, however API calls have different meaning
# using e.g. a display method locally should immediately display the result, while using it through the plugin system
# should result in a oneway call to display on the remote


__fake_usr_data = {}
# fake user persistent data to allow for consistent behavior and testing without server

class BaseAPI:
    """
    Base class for all API objs. Simultaneously fallback for calls where no API was passed.

    API objs only exist asynchroniously. Sync calls will be wrapped.
    The API implementation is provided by a server on which the plugin system runs.
    It's primary function is to access webserver functionality. For development and consistency reasons,
    serverless API exists as well. This is the base and fallback for all API calls.
    It serves API calls with minimal compatibility, i.e. it just prints the result.

    The API implementation assumes a django server, although as mentioned it is not a requirement.
    """
    def __init__(self, request_id, identity, call_type):
        self.request_id = request_id
        self.identity = identity
        self.call_type = call_type

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


class PublicSyncApi(BaseAPI):
    """
    API class for public sync calls.

    Abstracts away the retrieval of the actual API obj stored in the context.
    """
    @staticmethod
    def get_call_api():
        global __plugin_ctx
        return __plugin_ctx.get()

    def __getattribute__(self, item):
        attr = super().__getattribute__(item)
        if callable(attr) and hasattr(BaseAPI, item) and not item.startswith("__"):
            api = PublicSyncApi.get_call_api()
            actual_api_method = getattr(api, item)
            return actual_api_method
        else:
            return attr

class RemoteAPI(BaseAPI):
    """
    API class for remote calls.

    Relays all calls to client for execution. Only exception is logging, which will be both logged locally and sent to
    the server.
    """
    def __getattribute__(self, item):
        attr = super().__getattribute__(item)
        if callable(attr) and hasattr(BaseAPI, item) and not item.startswith("__"):
            _memory.server.send_api_call(self.request_id, self.identity, item)


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




__plugin_ctx = contextvars.ContextVar('__plugin_api', default=BaseAPI(0, 0, 0))
"""If you don't know what this does, you should probably not touch it"""


# set ctx vars for API
def _call_function(func, args, kwargs, request_id, identity, callstack_type : CallstackType):
    call_api = BaseAPI(request_id, identity)
    # if callstack_type & CallstackType.LOCAL:
    #     if callstack_type & CallstackType.ASYNCIO:

    __plugin_ctx.set(call_api)

    return __plugin_ctx.run(func, *args, **kwargs)
