import hashlib
import importlib
import os.path
import sys
import threading

from rixaplugin.pylot.proxy_builder import create_module
from rixaplugin.pylot.python_parsing import generate_python_doc
import zmq.asyncio as aiozmq
import logging
from rixaplugin.data_structures.enums import FunctionPointerType, HeaderFlags
import secrets
from rixaplugin.data_structures.rixa_exceptions import FunctionNotFoundException, PluginNotFoundException

core_log = logging.getLogger("rixa.core")
from rixaplugin import settings
from rixaplugin.internal import utils


def get_function_entry(name, plugin_name=None):
    if not plugin_name:
        filtered_entries = [d for d in _memory.function_list if d.get("name") == name]
        if len(filtered_entries) > 1:
            raise Exception("Multiple functions with same name found. Specify plugin name to resolve ambiguity.")
        if len(filtered_entries) == 0:
            raise FunctionNotFoundException(name)
        return filtered_entries[0]
    else:
        plugin_entry = _memory.plugins.get(plugin_name, None)
        if not plugin_entry:
            raise PluginNotFoundException(plugin_name)
        filtered_entries = [d for d in plugin_entry["functions"] if d.get("name") == name]
        if len(filtered_entries) == 0:
            raise FunctionNotFoundException(f"Plugin '{plugin_name}' found, but not function: '{name}'")
        return filtered_entries[0]




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
        self.global_init = []
        self.worker_init = []
        self.listener_socket = None
        self.event_loop = None
        self.is_clean = False
        self.lock = threading.Lock()
        self.__zmq_context = None
        self._client_connections = set()
        self.debug_mode = settings.DEBUG
        self.server = None
        self.main_thread_id = threading.get_ident()

        self.tasks_in_system = 0

        self.connected_clients = []

        id_str = os.path.abspath(__file__) + str(sys.implementation) + str(sys.prefix)
        hash_object = hashlib.sha256(id_str.encode())
        hex_dig = hash_object.hexdigest()
        self.ID = hex_dig[:16]

        # self.ID = secrets.token_hex(8)
        self.max_queue = 10
        self.allow_remote_functions = True if settings.ACCEPT_REMOTE_PLUGINS != 0 else False
        self.remote_dummy_modules = {}

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
        if not self.allow_remote_functions:
            return
        local_plugin_names = [i["name"] for i in self.plugins.values() if i["type"] & FunctionPointerType.LOCAL]

        # add functions to function list
        new_names = []
        to_pop = []
        for i in plugin_dict.values():
            if i["name"] in local_plugin_names:
                core_log.warning(f"Plugin '{i['name']}' already exists locally. Skipping...")
                to_pop.append(i["name"])
                continue
            if i["name"] in self.plugins:
                # print(i["name"])
                # print(self.plugins[i["name"]]["id"].decode())
                # print(i["id"])
                if self.plugins[i["name"]]["id"] == i["id"]:
                    core_log.debug(f"Plugin '{i['name']}' updated")
                else:
                    to_pop.append(i["name"])
                    core_log.error(f"Plugin '{i['name']}' already exists with different ID. Skipping...")
                    continue
                del self.plugins[i["name"]]
                self.function_list = [j for j in self.function_list if j["plugin_name"] != i["name"]]
            new_names.append(i["name"])
            i["id"] = i["id"] #identity
            i["remote_id"] = identity
            i["remote_origin"] = remote_origin
            if origin_is_client:
                i["type"] |= FunctionPointerType.CLIENT
            else:
                i["type"] |= FunctionPointerType.SERVER
            for j in i["functions"]:
                j["type"] = i["type"]
                j["id"] = i["id"]#identity
                j["remote_id"] = identity
                j["remote_origin"] = remote_origin
                self.function_list.append(j)
            # remote_plugin_to_module(i)

        # if settings.MAKE_REMOTES_IMPORTABLE:
        #     for name, plugin in plugin_dict.items():
        #         if name in self.remote_dummy_modules:
        #             from rixaplugin.internal import api
        #             remote_module = create_module("rixaplugin.remote" + name, plugin["functions"],
        #                                           function_factory=api.relay_module)
        #             old_module = self.remote_dummy_modules[name]
        #             self.remote_dummy_modules[name] = remote_module
        #             # importlib.reload(remote_module)
        #             old_module_dict = old_module.__dict__
        #             old_module_dict.clear()
        #             old_module_dict.update(remote_module.__dict__)
        plugin_dict = {k: v for k, v in plugin_dict.items() if k not in to_pop}
        if new_names:
            core_log.debug("Received new plugins: " + ", ".join(new_names))
        self.plugins = {**self.plugins, **plugin_dict}

    def delete_plugin(self, name):
        if name in self.plugins:
            del self.plugins[name]
            self.function_list = [i for i in self.function_list if i["plugin_name"] != name]

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
        # w_counts = self.executor.get_free_and_active_worker_count()
        readable_str += f"{_memory.executor.get_active_task_count()}/{_memory.executor.get_max_task_count()} tasks running\n" if self.executor else "No executor\n"
        readable_str += f"{_memory.executor.get_queued_task_count()} tasks additional tasks queued\n" if self.executor else ""
        # readable_str += "Max queue size: " + str(self.max_queue) + "\n" if self.executor else ""
        readable_str += "\nPlugins:\n" + self.pretty_print_plugins()
        return readable_str

    def pretty_print_plugins(self):
        readable_str = "Plugin info:\n---------\n"
        for name, entry in self.plugins.items():
            readable_str += self._pretty_print_plugin(entry)
        return readable_str

    def _pretty_print_plugin(self, entry):
        readable_str = ""
        readable_str += f"Name: {entry['name']}\nID: {'LOCAL' if entry['type'] & FunctionPointerType.LOCAL else entry['id']}," \
                        f" TYPE:{entry['type']}, ALIVE:{entry['is_alive']}, N_TASKS: {entry['active_tasks']}\n"
        for i in entry["functions"]:
            readable_str += f"\t{generate_python_doc(i, include_docstr=False)}\n"
        return readable_str

    def pretty_print_plugin(self, plugin_name):
        readable_str = ""
        entry = self.plugins.get(plugin_name)
        if not entry:
            return "Plugin not found"
        readable_str += self._pretty_print_plugin(entry)
        return readable_str

    def get_sendable_plugins(self, remote_id=-1, skip=None):
        if skip is None:
            skip = []
        sendable_dict = {}

        for key, value in self.plugins.items():
            if key in skip:
                continue
            if value["is_alive"] is False:
                continue
            if value["type"] & FunctionPointerType.REMOTE and not settings.ALLOW_NETWORK_RELAY:
                continue
            if "id" in value and value["id"] == remote_id:
                continue

            sendable_plugin = value.copy()
            if sendable_plugin["type"] & FunctionPointerType.LOCAL:
                sendable_plugin["type"] = FunctionPointerType.REMOTE
            elif sendable_plugin["type"] & FunctionPointerType.REMOTE:
                sendable_plugin["type"] = FunctionPointerType.INDIRECT | FunctionPointerType.REMOTE

            sendable_plugin["functions"] = [j for j in sendable_plugin["functions"] if
                                            not j["type"] & FunctionPointerType.LOCAL_ONLY]

            sendable_dict[key] = sendable_plugin

        # clean up i.e. remove pointers and other unnecessary data from function entries
        for key, val in sendable_dict.items():
            val["functions"] = [j.copy() for j in val["functions"]]
            # val.pop("id", None)
            val.pop("remote_origin", None)
            for j in val["functions"]:
                j.pop("pointer", None)
                j.pop("remote_id", None)
                j.pop("remote_origin", None)
                if j["type"] & FunctionPointerType.LOCAL:
                    j["type"] = FunctionPointerType.REMOTE
                elif j["type"] & FunctionPointerType.REMOTE:
                    j["type"] = FunctionPointerType.INDIRECT | FunctionPointerType.REMOTE

        sendable_dict = {k: v for k, v in sendable_dict.items() if v["functions"]}

        return sendable_dict

    def get_functions(self, excluded_functions = None, excluded_plugins = None, short=False,
                      inclusive_tags = None, exclusive_tags = None):
        func_str = ""
        #        for i in entry["functions"]:
        #    readable_str += f"\t{generate_python_doc(i, include_docstr=False)}\n"
        for key, val in self.plugins.items():
            if excluded_plugins and key in excluded_plugins:
                continue
            if val["is_alive"] is False:
                continue
            for j in val["functions"]:
                if excluded_functions and j["name"] in excluded_functions:
                    continue
                if inclusive_tags:
                    if not j.get("tags") or not any([i in j["tags"] for i in inclusive_tags]):
                        continue
                if exclusive_tags:
                    if j.get("tags") and any([i in j["tags"] for i in exclusive_tags]):
                        continue
                func_str += generate_python_doc(j, include_docstr=True, short=short) + "\n\n"
        return func_str

    def clean(self):
        with self.lock:
            if self.is_clean:
                print("Already clean")
                return
            utils.remove_plugin(self.ID)
            self.is_clean = True
            try:
                if self.executor:
                    self.executor.shutdown()
                if self.listener_socket:
                    self.listener_socket.close()
                for i in self._client_connections:
                    i.close()
                if self.zmq_context:
                    if self.server:
                        if self.server.use_curve:
                            self.server.auth.stop()
                    self.zmq_context.term()
            except:
                pass

    @staticmethod
    def purge():
        PluginMemory._instance.clean()
        PluginMemory._instance = None
        PluginMemory()

_memory = PluginMemory()






