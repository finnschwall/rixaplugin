import time
import multiprocessing as mp
import json
import uuid
from concurrent.futures import ThreadPoolExecutor, ProcessPoolExecutor, Future
import threading
import queue
import pickle
from .proxy_builder import construct_importable
import warnings
import msgpack
from .memory import _memory
from .enums import HeaderFlags
import zmq.auth
import logging
from .utils import *

import asyncio
import zmq
import zmq.asyncio as aiozmq

# logging.basicConfig(level=logging.DEBUG)
network_log = logging.getLogger("net")


# network_log.setLevel(0)
# network_log.addHandler(logging.FileHandler("network.log"))


async def create_and_start_plugin_server(port, address=None, name=None, allow_any_connection=False):
    if allow_any_connection:
        network_log.warning("Allowing any connection to the server. Disable for production!")
        # warnings.warn("Allowing any connection to the server. Disable for production!")
    else:
        # TODO curve pair check
        raise NotImplementedError()
    if _memory.server:
        raise Exception("Server already running")
    server = PluginServer(port, address, name=name, use_curve=not allow_any_connection)
    future = _memory.event_loop.create_task(server.listen())
    _memory.server = server
    return server, future

class NetworkAdapter:
    # unify client and server/abstract those parts that are present in both.
    # this is now meant purely low level so no reference to the _memory object
    def __init__(self, zmq_ctx, port, name, use_curve=True):
        self.zmq_ctx = zmq_ctx
        self.port = port
        self.name = name
        self.use_curve = use_curve
        self.con = None
        self.error_count = 0

    async def send_return(self, identity, request_id, ret):
        ret = {"HEAD": HeaderFlags.FUNCTION_RETURN, "return": ret, "request_id": request_id}
        try:
            raw = msgpack.packb(ret)
        except Exception as e:
            network_log.exception(f"Function return not serializable")
            await self.send_exception(identity, request_id, e)
            return
        await self.con.send_multipart([identity, raw])

    async def send_exception(self, identity, request_id, exception):
        ret = {"HEAD": HeaderFlags.EXCEPTION_RETURN, "exception": exception, "request_id": request_id}
        await self.con.send_multipart([identity, msgpack.packb(ret)])

    async def send_api_call(self, identity, request_id, api_func_name, args, kwargs):
        ret = {"HEAD": HeaderFlags.API_CALL, "api_func_name": api_func_name, "args": args, "kwargs": kwargs,
               "request_id": request_id}
        await self.con.send_multipart([identity, msgpack.packb(ret)])


    @staticmethod
    def generate_curve_keys(self, key_dir):
        s_pub, s_sec = zmq.auth.create_certificates(key_dir, "server")
        c_pub, c_sec = zmq.auth.create_certificates(key_dir, "client")
        return {"server": (s_pub, s_sec), "client": (c_pub, c_sec)}


class PluginServer:

    def __init__(self, port, address=None, name=None, use_curve=True):
        # TODO implement curve via https://gist.github.com/mivade/97c2dc353a1bb460a1d44010df66e6d7
        # try to get the name of this plugin
        if not name:
            self.name = _memory.name
        else:
            self.name = name
        network_log.debug("Starting server")
        self.con = _memory.zmq_context.socket(zmq.ROUTER)
        _memory.listener_socket = self.con
        self.error_count = 0

        if not address:
            address = f"tcp://*:{port}"
        self.con.bind(address)
        network_log.debug(f"Server started at {address}")

    async def send_return(self, identity, request_id, ret):
        ret = {"HEAD": HeaderFlags.FUNCTION_RETURN, "return": ret, "request_id": request_id}
        print(identity)
        try:
            raw = msgpack.packb(ret)
        except Exception as e:
            network_log.exception(f"Function return not serializable")
            await self.send_exception(identity, request_id, e)
            return
        await self.con.send_multipart([identity, raw])

    async def send_exception(self, identity, request_id, exception):
        ret = {"HEAD": HeaderFlags.EXCEPTION_RETURN, "exception": exception, "request_id": request_id}
        await self.con.send_multipart([identity, msgpack.packb(ret)])

    async def send_api_call(self, identity, request_id, api_func_name, args, kwargs):
        ret = {"HEAD": HeaderFlags.API_CALL, "api_func_name": api_func_name, "args": args, "kwargs": kwargs,
               "request_id": request_id}
        await self.con.send_multipart([identity, msgpack.packb(ret)])

    async def listen(self):
        while True:
            print("A")
            identity, message = await self.con.recv_multipart()
            print("B", flush=True)
            try:
                network_log.debug(f"Received something from {identity.hex()}")
                try:
                    msg = msgpack.unpackb(message)
                    print(msg)
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
                except:
                    network_log.warning("Received message header is not a valid flag!")
                    continue
                if header_flags & HeaderFlags.ACKNOWLEDGE:
                    network_log.debug(f"Acknowledging connection")
                    ret = {"HEAD": HeaderFlags.ACKNOWLEDGE | HeaderFlags.SERVER}
                    if "request_info" in msg and msg["request_info"] == "plugin_signatures":
                        ret["plugin_signatures"] = _memory.sendable_function_list
                    if "request_info" in msg:
                        ret["name"] = self.name
                    await self.con.send_multipart(
                        [identity, msgpack.packb(ret)])

                if "node_count" in msg:
                    if msg["node_count"] > 5:
                        network_log.warning(
                            f"Deadlock detected. Too many nodes visited. Function call stack is circular."
                            f"Most likely a user error. Message will be ignored.")
                        continue
                elif header_flags & HeaderFlags.FUNCTION_CALL:
                    network_log.debug(f"Received function call from {identity.hex()}")
                    try:
                        future = asyncio.create_task(execute_local(
                            msg["func_name"], msg["args"], msg["kwargs"], identity, msg["request_id"], 3, False))
                        ret = {"HEAD": HeaderFlags.TIME_ESTIMATE_AND_ACKNOWLEDGEMENT, "request_id": msg["request_id"]}
                        await self.con.send_multipart([identity, msgpack.packb(ret)])
                    except FunctionNotFoundException as e:
                        ret = {"HEAD": HeaderFlags.FUNCTION_NOT_FOUND, "request_id": msg["request_id"]}
                        await self.con.send_multipart([identity, msgpack.packb(ret)])
            except Exception as e:
                network_log.error(f"Message header faulty: Error:\n{e}")
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


async def create_and_start_plugin_client(server_address, port=2809, raise_on_connection_failure=True, name=None):
    client = PluginClient(server_address, port)
    try:
        client.con.connect(client.full_address)
        packed_msg = msgpack.packb(
            {"HEAD": HeaderFlags.ACKNOWLEDGE | HeaderFlags.CLIENT, "request_info": "plugin_signatures"})
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
            print(msg)
            if msg["HEAD"] & HeaderFlags.ACKNOWLEDGE:
                network_log.debug("Connection established")
            else:
                raise Exception(
                    "Connection established but failed to receive acknowledge message. This shouldn't happen.")
            client.remote_function_signatures = msg.get("plugin_signatures")
            if not name:
                client.name = msg.get("name")
            else:
                client.name = name
        except zmq.ZMQError as e:
            if raise_on_connection_failure:
                raise Exception(f"Failed to connect to {client.full_address}: {e}")
            else:
                network_log.warning("Connection established but failed to receive acknowledge message."
                                    "This shouldn't happen.")
                return None
    except zmq.ZMQError as e:
        raise Exception(f"Failed to connect to {server_address}:{port}\n{e}")
    future = asyncio.create_task(client._response_listener())
    asyncio.create_task(supervise_future(future))
    return client, future


class PluginClient:

    def __init__(self, server_address, port, protocoll="tcp://"):
        self.full_address = f"{protocoll}{server_address}:{port}"
        self.con = _memory.add_client_connection(zmq.DEALER)
        self.pending_requests = {}
        self.time_estimate_events = {}
        self.time_estimate = {}
        self.remote_function_signatures = None
        self.name = None

    def __del__(self):
        _memory.delete_connection(self.con)

    def reconnect(self):
        raise NotImplementedError()

    def add_remote_to_modules(self):

        if not self.name:
            name = "rixa_remote"
            warnings.warn("No name set for remote plugin. Any other nameless plugin loaded before will be overwritten.")
        else:
            name = self.name

        construct_importable(name, self.remote_function_signatures, description="Remote plugin module")

    async def call_remote_function(self, func_name, args=None, kwargs=None, one_way=False, return_time_estimate=False):
        if args is None:
            args = []
        if kwargs is None:
            kwargs = {}

        request_id = identifier_from_signature(func_name, args, kwargs)
        message = {
            "HEAD": HeaderFlags.FUNCTION_CALL,
            "request_id": request_id,
            "func_name": func_name,
            "args": args,
            "kwargs": kwargs
        }

        event = asyncio.Event()
        self.time_estimate_events[request_id] = event

        future = _memory.event_loop.create_future()
        if not one_way:
            self.pending_requests[request_id] = future
        else:
            self.pending_requests[request_id] = None

        serialized_message = msgpack.packb(message)

        await self.con.send(serialized_message)

        # time estimate is alway awaited
        # need to check whether this makes sense or if call without acknowledgement is possible
        await event.wait()

        time_estimate = self.time_estimate[request_id]
        del self.time_estimate[request_id]
        del self.time_estimate_events[request_id]

        if return_time_estimate:
            return future, time_estimate
        if one_way:
            return None
        return future

    async def _response_listener(self):
        while True:
            try:
                response = await self.con.recv()
                try:
                    message = msgpack.unpackb(response)
                    print(message)
                except Exception as e:
                    network_log.warning(f"Received message is not in msgpack format: {e}")
                    continue
                if "HEAD" not in message:
                    network_log.warning("Received message does not contain a header!")
                    continue
                try:
                    header_flags = HeaderFlags(message["HEAD"])
                    print(header_flags)
                except:
                    network_log.warning("Received message header is not a valid flag!")
                    continue
                if header_flags & HeaderFlags.FUNCTION_RETURN:
                    request_id = message.get("request_id")
                    if request_id in self.pending_requests:
                        if not self.pending_requests[request_id]:
                            del self.pending_requests[request_id]
                            continue
                        ret_val = message.get("return")
                        if ret_val:
                            self.pending_requests[request_id].set_result(ret_val)
                        if "exception" in message:
                            ret_val = Exception("Something went wrong on the server side.")
                            self.pending_requests[request_id].set_exception(ret_val)
                        del self.pending_requests[request_id]
                    else:
                        network_log.warning(f"Received response for unknown request id: {request_id}")
                elif header_flags & HeaderFlags.TIME_ESTIMATE_AND_ACKNOWLEDGEMENT:
                    request_id = message.get("request_id")
                    print(self.time_estimate_events)
                    if request_id in self.time_estimate_events:
                        self.time_estimate[request_id] = message.get("time_estimate")
                        self.time_estimate_events[request_id].set()
                    else:
                        network_log.warning(f"Received time estimate for unknown request id: {request_id}")
            except Exception as e:
                network_log.error(f"Something unexpected happened while parsing response:\n{e}")


def generate_public_keypair():
    """
    Generate a public keypair for the plugin server.
    :return: public key, secret key
    """
    raise NotImplementedError("Not tested yet!")
    public, secret = zmq.curve_keypair()
    return public, secret


def generate_client_keypair():
    """
    Generate a public keypair for the plugin client.
    :return: public key, secret key
    """
    raise NotImplementedError("Not tested yet!")
    public, secret = zmq.curve_keypair()
    return public, secret


from .executor import execute_local, FunctionNotFoundException
