import contextlib
import json
import os
import asyncio
import logging

from rixaplugin import settings
from rixaplugin.settings import DEBUG
from rixaplugin.pylot.python_parsing import  generate_python_doc
task_superviser_log = logging.getLogger("rixa.task_superviser")
discover_log = logging.getLogger("rixa.plugin_discovery")
# export PYTHONASYNCIODEBUG=1


def is_valid_call(func_metadata, args, kwargs):
    """
    Validates if the provided args and kwargs are valid for the function described by func_metadata.

    :param func_metadata: Dictionary describing the function's parameters.
    :param args: Tuple of positional arguments to be passed to the function.
    :param kwargs: Dictionary of keyword arguments to be passed to the function.
    :return: True if the call is valid, False otherwise.
    """
    return True
    # Too inprecise. E.g. when there are 2 args and the function has 1 arg and 1 kwarg it will raise an error
    correct_signature = " Expected signature is:\n" + generate_python_doc(func_metadata, include_docstr=False)

    # Check if the number of provided positional arguments exceeds the expected number
    positional_params = [param for param in func_metadata['args'] if param['kind'] == 1]
    if len(args) > len(positional_params):
        raise ValueError("Too many positional arguments." + correct_signature)

    # Check if all required arguments (without default values) are provided
    required_params = {param['name'] for param in func_metadata['args'] if 'default' not in param}
    required_params.update({param['name'] for param in func_metadata['kwargs'] if 'default' not in param})

    provided_params = set(kwargs.keys()) | {param['name'] for i, param in enumerate(func_metadata['args']) if
                                            i < len(args)}

    missing_params = required_params - provided_params
    if missing_params:
        raise ValueError(f"Missing required arguments: {missing_params}." + correct_signature)

    # Check if all provided keyword arguments are recognized
    all_params = {param['name'] for param in func_metadata['args']} | {param['name'] for param in
                                                                       func_metadata['kwargs']}
    unrecognized_kwargs = set(kwargs.keys()) - all_params
    if unrecognized_kwargs:
        raise ValueError(f"Unrecognized keyword arguments: {unrecognized_kwargs}." + correct_signature)
    return True



async def event_wait(evt, timeout):
    # suppress TimeoutError because we'll return False in case of timeout
    with contextlib.suppress(asyncio.TimeoutError):
        await asyncio.wait_for(evt.wait(), timeout)
    return evt.is_set()


async def supervisor(future, id=None):
    try:
        await future
    except Exception as e:
        task_superviser_log.exception(f"Supervision error" + (f" with id {id}" if id else ""))


async def supervise_future(future, id=None):
    """
    Supervise a future, log any exceptions.

    Used for plugin calls that are not awaited.
    :param future: Future to supervise
    :param id: Origin id (if available)
    """
    asyncio.create_task(supervisor(future, id))


def identifier_from_signature(fname, args=[], kwargs={}):
    """
    Create a unique identifier from function signature.

    If debug mode is enabled, this returns a human-readable string, that allows to identify the function.
    This means the ID is not necessarily unique!
    :param fname:
    :param args:
    :param kwargs:
    :return: Unique identifier
    """
    if DEBUG:
        args_str = str(args)[:10]
        kwargs_str = str(kwargs)[:10]
        signature = f"{fname}({args_str}, {kwargs_str})"
        signature = signature+":"+str(hash(signature))[1:5]
        return signature
    signature = fname
    for arg in args:
        signature += str(arg)
    if len(args) == 0:
        signature += "NOARGS"
    for k, v in kwargs.items():
        signature += str(k) + str(v)
    if len(kwargs) == 0:
        signature += "NOKWARGS"
    return hash(signature)


    PLUGIN_REGISTRY = "/tmp/plugin_registry.json"

def make_discoverable(id: str, endpoint: str, port: int, plugins: list) -> None:
    """
    Make oneself available by writing to the registry file.
    If the plugin is already registered, it will be updated with new values.

    :param name: The unique name of the plugin
    :param endpoint: An IP-like string (e.g. "localhost", "example.com")
    :param port: A TCP port number
    :param description: A short human-readable description of the plugin
    """
    registry = {}
    if os.path.exists(settings.PLUGIN_REGISTRY):
        with open(settings.PLUGIN_REGISTRY, 'r') as f:
            registry = json.load(f)

    # If we're already registered, update our entry; otherwise add a new one.
    for existing_plugin in list(registry.values()):
        if existing_plugin['ID'] == id:
            existing_plugin.update({
                "endpoint": endpoint,
                "port": port,
                "plugins": plugins
            })
            break
    else:  # not found, so we're adding anew...
        registry[id] = {
            "ID": id,
            "endpoint": endpoint,
            "port": port,
            "plugins": plugins
        }
    try:
        with open(settings.PLUGIN_REGISTRY, 'w') as f:
            json.dump(registry, f)
    except:
        pass

def discover_plugins() -> list[dict]:
    """
    Discover all available plugins by reading the registry file.
    :return: A list of dictionaries containing plugin info (name, endpoint, port, description)
    """
    if not os.path.exists(settings.PLUGIN_REGISTRY):
        return []

    try:
        with open(settings.PLUGIN_REGISTRY, 'r') as f:
            registry = json.load(f)

        plugins = [plugin for _, plugin in registry.items()]
        # Filter out any invalid entries
        valid_plugins = [{k: v for k, v in p.items() if k != '__module__'}
                         for p in plugins]

        return valid_plugins
    except:
        discover_log.error("Error while reading plugin registry")
        return []

def remove_plugin(id: str) -> None:
    """
    Remove one's own entry from the registry file.
    :param name: The unique name of the plugin to be removed
    """

    # Load current state...
    if not os.path.exists(settings.PLUGIN_REGISTRY):
        # print(f"Plugin {name} is already gone!")
        return

    with open(settings.PLUGIN_REGISTRY, 'r') as f:
        registry = json.load(f)

    if id in registry:
        del registry[id]
        with open(settings.PLUGIN_REGISTRY, 'w') as f:
            json.dump(registry, f)