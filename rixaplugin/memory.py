import threading
from .python_parsing import generate_python_doc
import zmq.asyncio as aiozmq
import logging
from .enums import FunctionPointerType
import secrets

core_log = logging.getLogger("core")
from . import settings


class PluginMemory:
    """Singleton class to store plugin information.

    DO NOT INSTANTIATE THIS CLASS DIRECTLY!
    Ensures access to variables is only possible from main thread and proper cleanup of resources."""
    _instance = None

    # def __new__(cls, *args, **kwargs):
    #     if not cls._instance:
    #         cls._instance = super(PluginMemory, cls).__new__(cls, *args, **kwargs)
    #     return cls._instance

    @property
    def zmq_context(self):
        if not self.__zmq_context:
            self.__zmq_context = aiozmq.Context()
        return self.__zmq_context

    def __init__(self):
        self.function_list = []
        self.plugins = {}
        self.plugin_system_active = False
        self.mode = None
        self.executor = None
        self.global_init = None
        self.worker_init = None
        self.listener_socket = None
        self.event_loop = None
        self.is_clean = False
        self.lock = threading.Lock()
        self.__zmq_context = None
        self._client_connections = set()
        self.debug_mode = False
        self.server = None
        self.ID = secrets.token_hex(8)
        self.max_queue = 10

    def add_function(self, signature_dict, id=None, fn_type=FunctionPointerType.LOCAL):
        if not id:
            id = self.ID
        self.function_list.append(signature_dict)
        if signature_dict["plugin_name"] in self.plugins:
            self.plugins[signature_dict["plugin_name"]]["functions"].append(signature_dict)
        else:
            # create a plugin entry
            plugin = {"name": signature_dict["plugin_name"], "functions": [signature_dict], "id": id,
                      "type": fn_type, "is_alive": True, "active_tasks": 0}
            self.plugins[signature_dict["plugin_name"]] = plugin

    def add_plugin(self, plugin_dict, identity, remote_origin, origin_is_client=False):
        # add functions to function list
        for i in plugin_dict.values():
            i["remote_id"] = identity
            i["remote_origin"] = remote_origin
            if origin_is_client:
                i["type"] |= FunctionPointerType.CLIENT
            else:
                i["type"] |= FunctionPointerType.SERVER
            for j in i["functions"]:
                j["type"] = i["type"]
                j["remote_id"] = identity
                j["remote_origin"] = remote_origin
                self.function_list.append(j)
        self.plugins = {**self.plugins, **plugin_dict}


    def add_remote_functions(self, func_list, plugin_id, origin_is_client=False):
        # DEPRECATED. Use add_plugin instead
        fn_type = FunctionPointerType.REMOTE
        if origin_is_client:
            fn_type |= FunctionPointerType.CLIENT
        else:
            fn_type |= FunctionPointerType.SERVER
        for i in func_list:
            i["type"] = fn_type
            i["pointer"] = plugin_id
            self.add_function(i, plugin_id, fn_type)
        #     self.function_list.append(i)
        #     remote_func_list.append(i)
        # remote_plugin = {"name": remote_name, "functions": remote_func_list, "id": plugin_id, "type": fn_type,
        #                  "is_alive": True, "active_tasks": 0}
        # self.plugins[remote_name] = remote_plugin

    def force_shutdown(self):
        core_log.error("Force shutdown of plugin system! This should not happen!")

        self.clean()
        # kill own process
        import os
        import signal
        os.kill(os.getpid(), signal.SIGKILL)

    def add_client_connection(self, scheme):
        with self.lock:
            client_socket = self.zmq_context.socket(scheme)
            self._client_connections.add(client_socket)
            return client_socket

    def delete_connection(self, con):
        with self.lock:
            con.close()
            self._client_connections.remove(con)

    def find_function_by_name(self, func_name):
        for i in self.function_list:
            if i.get("name") == func_name:
                return i
        return None

    def __repr__(self):
        return f"{self.__class__.__name__}({self.function_list!r})"

    def __str__(self):
        # readable_str = "\n".join([str(i) + ": " + str(d) for i, d in enumerate(self.function_list, 1)])
        readable_str = f"Mode: {self.mode}, ID: {self.ID}, Debug: {self.debug_mode}\n"
        readable_str += f"{self.executor.queue.qsize()} tasks in queue\n" if self.executor else "No executor\n"
        readable_str += "Max queue size: " + str(self.max_queue) + "\n" if self.executor else ""
        readable_str += "\nPlugins:\n" + self.pretty_print_plugins()
        return readable_str

    def pretty_print_plugins(self):
        readable_str = ""
        for name, entry in self.plugins.items():
            readable_str += f"{name}\nID:..{entry['id'][-5:]}, TYPE:{entry['type']}, ALIVE:{entry['is_alive']}, N_TASKS: {entry['active_tasks']}\n"
            for i in entry["functions"]:
                readable_str += f"\t{generate_python_doc(i, include_docstr=False)}\n"
        return readable_str


    def get_sendable_plugins(self, remote_id=-1):
        sendable_dict = {}

        for key, value in self.plugins.items():
            if value["type"] & FunctionPointerType.REMOTE and not settings.ALLOW_NETWORK_RELAY:
                continue
            # prevent the remote plugin from receiving its own functions
            if value["id"] == remote_id:
                continue
            sendable_plugin = value.copy()
            if sendable_plugin["type"] & FunctionPointerType.LOCAL:
                sendable_plugin["type"] = FunctionPointerType.REMOTE
            elif sendable_plugin["type"] & FunctionPointerType.REMOTE:
                sendable_plugin["type"] = FunctionPointerType.INDIRECT | FunctionPointerType.REMOTE
            sendable_dict[key] = sendable_plugin

        # clean up i.e. remove pointers and other unnecessary data from function entries
        for key,val in sendable_dict.items():
            val["functions"] = [j.copy() for j in val["functions"]]
            for j in val["functions"]:
                j.pop("pointer", None)
                if j["type"] & FunctionPointerType.LOCAL:
                    j["type"] = FunctionPointerType.REMOTE
                elif j["type"] & FunctionPointerType.REMOTE:
                    j["type"] = FunctionPointerType.INDIRECT | FunctionPointerType.REMOTE

        return sendable_dict

    def get_sendable_func_list(self, remote_id):
        # DEPRECATED AND TO BE REMOVED. Use get_sendable_plugin_list instead
        if settings.ALLOW_NETWORK_RELAY:
            # only send functions that are not remote
            sendable_list = []
            for i in self.function_list:
                if i["type"] & FunctionPointerType.REMOTE:
                    continue
                sendable_dict = i.copy()
                sendable_dict.pop("pointer")
                sendable_list.append(sendable_dict)
            return sendable_list

        sendable_list = []
        for i in self.function_list:
            sendable_dict = i.copy()
            sendable_dict.pop("pointer")
            sendable_list.append(sendable_dict)
        return sendable_list

    def clean(self):
        with self.lock:
            if self.is_clean:
                print("Already clean")
                return
            self.is_clean = True
            if self.executor:
                self.executor.shutdown()
            if self.listener_socket:
                self.listener_socket.close()
            for i in self._client_connections:
                i.close()
            if self.zmq_context:
                self.zmq_context.term()

    def __del__(self):
        self.clean()

    @staticmethod
    def purge():
        PluginMemory._instance.clean()
        PluginMemory._instance = None
        PluginMemory()


_memory = PluginMemory()
