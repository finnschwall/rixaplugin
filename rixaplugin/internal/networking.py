import pickle

import msgpack
import msgpack_numpy


import rixaplugin.internal.rixalogger
from rixaplugin.internal import utils
from rixaplugin.internal.memory import _memory
from rixaplugin.data_structures.enums import HeaderFlags

import zmq.auth

from rixaplugin.data_structures.rixa_exceptions import RemoteException, RemoteTimeoutException, \
    RemoteUnavailableException
from rixaplugin.internal.utils import *
import asyncio
import zmq
msgpack_numpy.patch()
# logging.basicConfig(level=logging.DEBUG)
network_log = logging.getLogger("rixa.plugin_net")


# network_log.setLevel(0)
# network_log.addHandler(logging.FileHandler("network.log"))


#bad hack but required for now
# msgpack.packb = pickle.dumps
# msgpack.unpackb = pickle.loads

def generate_curve_keys(key_dir):
    s_pub, s_sec = zmq.auth.create_certificates(key_dir, "server")
    c_pub, c_sec = zmq.auth.create_certificates(key_dir, "client")
    return {"server": (s_pub, s_sec), "client": (c_pub, c_sec)}


async def create_and_start_plugin_server(port, address=None, allow_any_connection=False):
    if allow_any_connection:
        network_log.warning("Allowing any connection to the server. Disable for production!")
        # warnings.warn("Allowing any connection to the server. Disable for production!")
    # else:
    #     # TODO curve pair check
    #     raise NotImplementedError()
    if _memory.server:
        raise Exception("Server already running")
    server = PluginServer(port, address, use_curve=not allow_any_connection, manually_created=False)
    future = _memory.event_loop.create_task(server.listen())
    _memory.server = server
    return server, future


class NetworkAdapter:
    # unify client and server/abstract those parts that are present in both.
    # this is now meant purely low level so no reference to the _memory object
    def __init__(self, port, use_curve=True, manually_created=True):
        self.port = port
        self.use_curve = use_curve
        self.con = None
        self.error_count = 0
        self.pending_requests = {}
        self.time_estimate_events = {}
        self.time_estimate = {}
        self.is_server = None
        self.is_initialized = False
        self.api_objs = {}

        if manually_created:
            network_log.warning("Manually created network adapter. No automatic resource management. Cleanup required!")



    async def send(self, identity, data, already_serialized=False):
        if not already_serialized:
            try:
                data = msgpack.packb(data)
                # data = pickle.dumps(data)
            except Exception as e:
                network_log.error(f"A message could not be serialized: {data}")
                # return
        if self.is_server:
            if identity==0:
                raise Exception("Identity is 0")
            await self.con.send_multipart([identity, data])
        else:
            await self.con.send(data)

    async def send_return(self, identity, request_id, ret):
        ret = {"HEAD": HeaderFlags.FUNCTION_RETURN, "return": ret, "request_id": request_id}
        try:
            raw = msgpack.packb(ret)
        except Exception as e:
            network_log.exception(f"Function return not serializable")
            await self.send_exception(identity, request_id, e)
            return
        await self.send(identity, raw, already_serialized=True)

    async def send_exception(self, identity, request_id, exception):
        # RemoteException(exception_info['type'], exception_info['message'], exception_info['traceback']
        if settings.LOG_REMOTE_EXCEPTIONS_LOCALLY:
            network_log.exception(f"Remote exception in {request_id}")
        exc_str = rixaplugin.internal.rixalogger.format_exception(exception, without_color=True)

        ret = {"HEAD": HeaderFlags.EXCEPTION_RETURN, "message": str(exception), "request_id": request_id,
               "type": type(exception).__name__, "traceback": exc_str}

        print("-------------")
        print(exception.__dict__)
        if isinstance(exception, RemoteUnavailableException):
            if exception.plugin_name:
                print("B")
                ret["offline_plugin_name"] = exception.plugin_name
        await self.send(identity, ret)


    async def send_api_call(self, identity, request_id, api_func_name, args, kwargs):
        ret = {"HEAD": HeaderFlags.API_CALL, "api_func_name": api_func_name, "args": args, "kwargs": kwargs,
               "request_id": request_id}
        await self.send(identity, ret)

    async def call_remote_function(self, plugin_entry, api_obj, args=None, kwargs=None,  one_way=False,
                                   return_time_estimate=False):

        if args is None:
            args = []
        if kwargs is None:
            kwargs = {}

        request_id = identifier_from_signature(plugin_entry["name"], args, kwargs)
        self.api_objs[request_id] = api_obj
        message = {
            "HEAD": HeaderFlags.FUNCTION_CALL,
            "request_id": request_id,
            "func_name": plugin_entry["name"],
            "plugin_name": plugin_entry["plugin_name"],
            "oneway": one_way,
            "args": args,
            "kwargs": kwargs
        }

        event = asyncio.Event()
        self.time_estimate_events[request_id] = event

        future = _memory.event_loop.create_future()
        if not one_way:
            self.pending_requests[request_id] = future

        remote_func_type = plugin_entry["type"]
        await self.send(plugin_entry["remote_id"], message)
        # time estimate is always awaited
        # need to check whether this makes sense or if call without acknowledgement is possible
        answer = await utils.event_wait(event, 3)  # event.wait()
        # print("----")
        # print(api_obj.__dict__)
        # print(api_obj.is_remote)
        if not answer:
            print("\n\n")
            print("NO ANSWER")
            print(plugin_entry["plugin_name"])
            _memory.plugins[plugin_entry["plugin_name"]]["is_alive"] = False

            del self.api_objs[request_id]
            # if api_obj.is_remote:
            #     api_obj.network_adapter.send_exception(api_obj.identity, request_id, Exception("Plugin offline"))
            #     # await self.send_exception(api_obj.remote_id, request_id, Exception("Plugin offline"))
            # else:
            raise RemoteTimeoutException(f"No acknowledgement for function call. Plugin '{plugin_entry['plugin_name']}' offline?",
                                         plugin_name=plugin_entry["plugin_name"])
        time_estimate = self.time_estimate[request_id]
        del self.time_estimate[request_id]
        del self.time_estimate_events[request_id]

        if return_time_estimate:
            return future, time_estimate
        if one_way:
            return None
        return future

    async def listen(self):
        while True:
            if self.is_server:
                identity, message = await self.con.recv_multipart()
                # network_log.debug(f"Received something from {identity.hex()}")
            else:
                message = await self.con.recv()
                identity = self
                # network_log.debug(f"Received something from remote on client {identity}")
            try:
                try:
                    msg = msgpack.unpackb(message)
                except:
                    network_log.warning("Received message is not in msgpack format!")
                    continue
                if not isinstance(msg, dict):
                    network_log.warning("Received message is not a dictionary!")
                    continue
                if "HEAD" not in msg:
                    network_log.warning("Received message does not contain a header!")
                    continue
                try:
                    header_flags = HeaderFlags(msg["HEAD"])
                    if self.is_server:
                        network_log.debug(f"Received {header_flags} from {identity.hex()}")
                    else:
                        network_log.debug(f"Received {header_flags} from remote on client {identity}")
                except:
                    network_log.warning("Received message header is not a valid flag!")
                    continue

                if "node_count" in msg:
                    if msg["node_count"] > 5:
                        network_log.warning(
                            f"Deadlock detected. Too many nodes visited. Function call stack is circular."
                            f"Most likely a user error. Message will be ignored.")
                        continue
                await self.handle_remote_message(header_flags, msg, identity)


            except Exception as e:
                network_log.exception(f"Network error:\n{e}")
                raise e
                self.error_count += 1
                if self.error_count > 10 and not _memory.debug_mode:
                    network_log.error("Incoming requests are invalid. This can't stem from this library. "
                                      "Is someone connecting to the wrong port?")
                elif self.error_count > 25 and not _memory.debug_mode:
                    network_log.error("Erroneous messages do not stop coming in. Is this a DOS attack?"
                                      "Shutting down immediately. Do not restart the server until the issue is resolved.")
                    _memory.force_shutdown()
                if self.error_count > 10 and _memory.debug_mode:
                    network_log.error("Too many errors while processing messages. Network headers are faulty")
                elif self.error_count > 100 and not _memory.debug_mode:
                    network_log.error("Incoming request are faulty and likely stem from erroneous code. Shutting down.")
                    _memory.force_shutdown()

    async def handle_remote_message(self, header_flags, msg, identity):
        if header_flags & HeaderFlags.ACKNOWLEDGE:
            network_log.debug(f"Acknowledging connection")
            ret = {"HEAD": HeaderFlags.ACKNOWLEDGE | HeaderFlags.SERVER, "ID": _memory.ID}

            if "request_info" in msg and msg["request_info"] == "plugin_signatures":
                if "plugin_signatures" in msg:
                    ret["plugin_signatures"] = _memory.get_sendable_plugins(skip=msg["plugin_signatures"].values())
                else:
                    ret["plugin_signatures"] = _memory.get_sendable_plugins()

            if "plugin_signatures" in msg:
                _memory.add_plugin(msg["plugin_signatures"], identity, self, origin_is_client=True)
            await self.send(identity, ret)
            self.first_connection.set()

            if settings.ALLOW_NETWORK_RELAY:
                # need to propagate new plugins to connected clients
                for client in _memory.connected_clients:
                    ret = {"HEAD": HeaderFlags.UPDATE_REMOTE_PLUGINS | HeaderFlags.SERVER, "ID": _memory.ID,
                           "plugin_signatures": _memory.get_sendable_plugins()}
                    await self.send(client, ret)

            _memory.connected_clients.append(identity)
        elif header_flags & HeaderFlags.UPDATE_REMOTE_PLUGINS:
            if "plugin_signatures" in msg:
                _memory.add_plugin(msg["plugin_signatures"], identity, self, origin_is_client=self.is_server)


        elif header_flags & HeaderFlags.FUNCTION_CALL:
            try:
                asyncio.create_task(execute_networked(
                    msg["func_name"], msg["plugin_name"], msg["args"], msg["kwargs"], msg["oneway"],
                    msg["request_id"], identity, self))
                ret = {"HEAD": HeaderFlags.TIME_ESTIMATE_AND_ACKNOWLEDGEMENT, "request_id": msg["request_id"]}
                await self.send(identity, ret)
            except FunctionNotFoundException as e:
                ret = {"HEAD": HeaderFlags.FUNCTION_NOT_FOUND, "request_id": msg["request_id"]}
                await self.send(identity, ret)

        elif header_flags & HeaderFlags.API_CALL:
            request_id = msg.get("request_id")
            api_obj = self.api_objs.get(request_id)
            if not api_obj:
                network_log.warning(f"API object not found for request id {request_id}")
                return
            api_func_name = msg.get("api_func_name")
            args = msg.get("args")
            kwargs = msg.get("kwargs")
            api_callable = getattr(api_obj, api_func_name)
            await api_callable(*args, **kwargs)

        elif header_flags & HeaderFlags.FUNCTION_RETURN:
            request_id = msg.get("request_id")
            asyncio.create_task(self.trigger_api_deletion(request_id))
            if request_id in self.pending_requests:
                if not self.pending_requests[request_id]:
                    del self.pending_requests[request_id]
                    return
                if "return" in msg:
                    ret_val = msg.get("return")
                    self.pending_requests[request_id].set_result(ret_val)
                if "exception" in msg:
                    ret_val = Exception("Something went wrong on the server side.")
                    self.pending_requests[request_id].set_exception(ret_val)
                del self.pending_requests[request_id]
            else:
                network_log.warning(f"Received response for unknown request id: {request_id}")

        elif header_flags & HeaderFlags.EXCEPTION_RETURN:
            request_id = msg.get("request_id")
            asyncio.create_task(self.trigger_api_deletion(request_id))
            exc = RemoteException(msg['type'], msg['message'], msg['traceback'])
            if request_id in self.pending_requests:
                if request_id in self.pending_requests:
                    self.pending_requests[request_id].set_exception(exc)
                    del self.pending_requests[request_id]
                else:
                    network_log.warning(f"Exception occured in one way call: {exc}")
            else:
                network_log.warning(f"Received exception for unknown request id: {exc}")
            if "offline_plugin_name" in msg:
                network_log.warning(f"Indirect remote plugin '{msg['offline_plugin_name']}' is offline")
                try:
                    _memory.plugins[msg["offline_plugin_name"]]["is_alive"] = False
                except Exception as e:
                    network_log.exception(f"Error setting plugin offline.")

        elif header_flags & HeaderFlags.TIME_ESTIMATE_AND_ACKNOWLEDGEMENT:
            request_id = msg.get("request_id")

            if request_id in self.time_estimate_events:
                self.time_estimate[request_id] = msg.get("time_estimate")
                self.time_estimate_events[request_id].set()
            else:
                network_log.warning(f"Received time estimate for unknown request id: {request_id}")

    async def trigger_api_deletion(self, request_id, time=2):
        """
        Trigger the deletion of an api object after a certain time.

        We can't del immediately as api calls can come after return due to async nature.
        :param request_id:
        :param time:
        :return:
        """
        await asyncio.sleep(time)
        if request_id in self.api_objs:
            del self.api_objs[request_id]


class PluginServer(NetworkAdapter):

    def __init__(self, port, address=None, use_curve=True, manually_created=True):
        # TODO implement curve via https://gist.github.com/mivade/97c2dc353a1bb460a1d44010df66e6d7
        super().__init__(port, use_curve, manually_created=manually_created)

        network_log.debug("Starting server")
        self.con = _memory.zmq_context.socket(zmq.ROUTER)
        _memory.listener_socket = self.con
        self.error_count = 0
        self.is_server = True

        if not address:
            address = f"tcp://*:{port}"
        self.con.bind(address)
        network_log.info(f"Server started at {address}")
        self.first_connection = asyncio.Event()
        utils.make_discoverable(_memory.ID, "localhost", port, list(_memory.plugins.keys()))


async def create_and_start_plugin_client(server_address, port=2809, raise_on_connection_failure=True, return_future=False):
    client = PluginClient(server_address, port, manually_created=False)
    try:
        client.con.connect(client.full_address)

        packed_msg = msgpack.packb(
            {"HEAD": HeaderFlags.ACKNOWLEDGE | HeaderFlags.CLIENT, "request_info": "plugin_signatures",
             "plugin_signatures": _memory.get_sendable_plugins(), "ID": _memory.ID, })
        await client.con.send(packed_msg)
        evts = await client.con.poll(1000)
        if evts == 0:
            addr = client.full_address
            del client
            if raise_on_connection_failure:
                raise Exception(f"Failed to connect to {addr}")
            else:
                return None
        try:
            message = await client.con.recv(zmq.NOBLOCK)
            msg = msgpack.unpackb(message)
            if msg["HEAD"] & HeaderFlags.ACKNOWLEDGE:
                network_log.info("Connection established")
            else:
                raise Exception(
                    "Connection established but failed to receive acknowledge message. This shouldn't happen.")

            _memory.add_plugin(msg.get("plugin_signatures"), client, client,
                               origin_is_client=False)


        except zmq.ZMQError as e:
            if raise_on_connection_failure:
                raise Exception(f"Failed to connect to {client.full_address}: {e}")
            else:
                network_log.warning("Connection established but failed to receive acknowledge message."
                                    "This shouldn't happen.")
                return None
    except zmq.ZMQError as e:
        raise Exception(f"Failed to connect to {server_address}:{port}\n{e}")
    future = _memory.event_loop.create_task(client.listen())
    if return_future:
        return client, future
    else:
        asyncio.create_task(supervise_future(future))
        return client

class PluginClient(NetworkAdapter):

    def __init__(self, server_address, port, protocoll="tcp://", use_curve=True, manually_created=True):
        super().__init__(port, use_curve, manually_created=manually_created)
        self.full_address = f"{protocoll}{server_address}:{port}"
        self.con = _memory.add_client_connection(zmq.DEALER)
        self.is_server = False

    def __del__(self):
        _memory.delete_connection(self.con)

    def __str__(self):
        return self.full_address

    def __repr__(self):
        return self.full_address

    def reconnect(self):
        raise NotImplementedError()

    # def add_remote_to_modules(self):
    #
    #     if not self.name:
    #         name = "rixa_remote"
    #         warnings.warn("No name set for remote plugin. Any other nameless plugin loaded before will be overwritten.")
    #     else:
    #         name = self.name
    #     construct_importable(name, self.remote_function_signatures, description="Remote plugin module")


from rixaplugin.internal.executor import execute_networked, FunctionNotFoundException
