import threading
from .proxy_builder import function_signature_from_spec
import zmq.asyncio as aiozmq
import logging
from . import settings

core_log = logging.getLogger("core")


def create_sendable_func_list(func_list):
    sendable_list = []
    for i in func_list:
        sendable_dict = i.copy()
        sendable_dict.pop("pointer")
        sendable_list.append(sendable_dict)
    return sendable_list


def filter_functions(func_list, *args, **kwargs):
    # TODO: Implement filtering
    return func_list


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
        self.name = None
        self.function_list = []
        self.sendable_function_list = []
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

    def add_function(self, signature_dict):
        self.function_list.append(signature_dict)
        sendable_dict = signature_dict.copy()
        sendable_dict.pop("pointer")
        self.sendable_function_list.append(sendable_dict)

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
        readable_str = "\n".join([function_signature_from_spec(i) for i in self.function_list])
        return f"{self.__class__.__name__} containing:\n{readable_str}"

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
