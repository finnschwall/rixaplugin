import math, psutil, os, sys, subprocess
import click
import warnings
import platform
from pprint import pprint
import importlib.util
import asyncio


@click.group()
def main():
    pass


@main.group(name="setup", help="Tools for setting up the plugin system.")
def setup():
    pass


@setup.command()
@click.argument("path", required=False)
def setup_work_dir(path=None):
    """
    Create a working directory in the specified path.

    Sets up all folders and files usually required for proper functioning of the plugin system.
    Do not use this command if you already have a working directory set up.
    :param path:
    :return:
    """
    if not path:
        path = os.getcwd()
    if click.confirm(f"Setting up working directory in '{path}'"):
        folders = ["auth_keys", "log"]
        for folder in folders:
            os.makedirs(os.path.join(path, folder), exist_ok=True)
        config_str = """[EXAMPLE SETTINGS]
DEBUG = True
USE_AUTH_SYSTEM = False
ALLOW_NETWORK_RELAY = False
LOG_EXCEPTIONS_LOCALLY = True
LOG_LEVEL=DEBUG"""
        with open(os.path.join(path, "config.ini"), 'w') as f:
            f.write(config_str)
        from rixaplugin.internal import networking
        # os.environ["RIXA_WD"] = path
        # networking.create_keys(server_keys=True)
        print("Working directory created in: ", path)


@setup.command(help="Generate keypair for authentication system. Keys are stored in the working directory.")
@click.argument("name", required=False)
def generate_auth_keys(name=None):
    from rixaplugin.internal import networking
    import os
    if name:
        networking.create_keys(name)
    else:
        networking.create_keys(server_keys=True)
    keys_folder = os.path.join(networking.settings.config_dir, 'auth_keys')
    print("Keys have been generated in: ", keys_folder)


async def run_server(debug):
    from rixaplugin import init_plugin_system, create_and_start_plugin_server
    from rixaplugin import PluginModeFlags as PMF
    import rixaplugin
    from rixaplugin import settings
    init_plugin_system(PMF.LOCAL | PMF.THREAD, debug=debug)
    server, future = await create_and_start_plugin_server(rixaplugin.settings.DEFAULT_PLUGIN_SERVER_PORT,
                                                          use_auth=settings.USE_AUTH_SYSTEM)
    print(f"Server started on {server.address}")
    await future


async def run_client(debug):
    from rixaplugin import init_plugin_system, create_and_start_plugin_client
    from rixaplugin import PluginModeFlags as PMF
    from rixaplugin import settings
    import rixaplugin
    init_plugin_system(PMF.LOCAL | PMF.THREAD, debug=debug)
    client, future = await create_and_start_plugin_client(rixaplugin.settings.PLUGIN_DEFAULT_ADDRESS,
                                                          rixaplugin.settings.PLUGIN_DEFAULT_PORT,
                                                          use_auth=settings.USE_AUTH_SYSTEM,
                                                          return_future=True)
    print(f"Client connected to {client.address}")
    await future


@main.command(help="Start a plugin server from a python file")
@click.argument("path", type=click.Path(exists=True))
@click.option("--port", help="Port to start server on")
@click.option("--debug", default=False, help="Activate debug mode")
@click.option("--address", default="localhost", help="Listen address of server")
def start_server(path, port=None, debug=None, address=None):
    setup_plugin_system(path, address, port, debug)
    asyncio.run(run_server(debug))


def setup_plugin_system(path, address=None, port=None, debug=None):
    import rixaplugin.settings as settings
    if port:
        settings.PLUGIN_DEFAULT_PORT = port
        settings.DEFAULT_PLUGIN_SERVER_PORT = port
    if address:
        settings.PLUGIN_DEFAULT_ADDRESS = address
    if debug:
        settings.DEBUG = debug

    if os.path.isdir(path):
        print("Not yet implemented.")
        return
    elif os.path.isfile(path):
        if path.endswith(".py"):
            python_file = path
        # check for .ini
        elif path.endswith(".ini"):
            print("Starting a client from a .ini file is not yet implemented.")
            return
        elif os.path.isfile(path + ".py"):
            python_file = path + ".py"
        else:
            raise ValueError("Unknown file type.")
    else:
        raise FileNotFoundError("File or directory not found.")
    filename = os.path.basename(python_file)
    plugin_spec = importlib.util.spec_from_file_location(filename, python_file)
    module = importlib.util.module_from_spec(plugin_spec)
    plugin_spec.loader.exec_module(module)
    if debug:
        print(
            f"Following things have been found in {python_file}: {[i for i in module.__dict__.keys() if not i.startswith('_')]}")


@main.command(help="Connect specified plugin to a server")
@click.argument("path", type=click.Path(exists=True))
@click.option("--address", default="localhost", help="Address of server")
@click.option("--port", help="Port of server")
@click.option("--debug", help="Activate debug mode")
def start_client(path, address=None, port=None, debug=None):
    setup_plugin_system(path, address, port, debug)
    asyncio.run(run_client(address))


@main.command(help="Retrieve all available functions from a server via quick connection")
@click.option("--address", default="localhost", help="Address of server")
@click.option("--port", default=15000, help="Port of server")
def get_available_functions(address, port):
    pass


@main.command(help="Discover all locally available plugin servers")
def discover_plugins():
    from rixaplugin.internal.utils import discover_plugins
    plugs = discover_plugins()
    pprint(plugs)


@setup.command(help="Gather system information")
@click.option("-v", '--verbose', is_flag=True, default=True)
def get_system_info(verbose):
    python_version = platform.python_version_tuple()

    if verbose:
        print(f"System interpreter: {sys.base_prefix == sys.prefix}")
        print(f"Python version: {python_version}")
        print(f"Architecture: {platform.machine()}")
        cur_platform = platform.system()
        print(f"Platform: {cur_platform}")
        print(f"Full platform: {platform.platform()}")

        try:
            result = subprocess.run(["which" if cur_platform == "Linux" else "where", 'python'], capture_output=True,
                                    text=True, check=False)
            str = '?????' if result.returncode != 0 else result.stdout.split('\n')[0]
        except Exception as e:
            str = e
        print(f"Sys python: {str}")

        try:
            config_dir = os.environ["RIXA_WD"]
            print(f"WD: {config_dir}")
            print(f"WD is env: True")
        except KeyError:
            current_directory = os.getcwd()
            files = os.listdir(current_directory)
            if "config.ini" in files:
                print(f"WD: {current_directory}")
                print(f"WD is env: False")
            else:
                print("WD: None")

        try:
            result = subprocess.run(["pyenv", 'root'], capture_output=True, text=True, check=False)
            str = 'No pyenv' if result.returncode != 0 else result.stdout.split('\n')[0]
        except:
            str = "No pyenv"
        print(f"Pyenv: {str}")
        try:
            result = subprocess.run(["conda", 'version'], capture_output=True, text=True, check=True)
            str = 'No Conda' if result.returncode != 0 else result.stdout.split('\n')[0]
        except:
            str = "No Conda"
        print(f"Conda: {str}")
        try:
            subprocess.check_output("make --version".split()).decode('ascii')
            print("Make: OK")
        except:
            print("Make: FAILED")
        try:
            subprocess.check_output("g++ --version".split()).decode('ascii')
            print("g++: OK")
        except:
            print("g++: FAILED")

        try:
            import math
            import psutil
            r1 = \
                subprocess.check_output("nvidia-smi --query-gpu=memory.free --format=csv".split()).decode(
                    'ascii').split(
                    '\n')[:-1][1]

            r2 = subprocess.check_output("nvidia-smi --query-gpu=memory.total --format=csv".split()).decode(
                'ascii').split('\n')[:-1][1]
            r3 = subprocess.check_output("nvidia-smi --query-gpu=count --format=csv".split()).decode(
                'ascii').split('\n')[:-1][1]
            r4 = subprocess.check_output("nvidia-smi --query-gpu=name --format=csv".split()).decode(
                'ascii').split('\n')[:-1][1]

            print(f"Number av GPUs: {r3}")
            print(f"Primary: {r4}")
            print(f"VRAM: {int(r1[:-3])}/{r2}")
            tot = round(psutil.virtual_memory()[1] / 1024 ** 2 + int(r1[:-3]))

        except Exception as e:
            print("No supported GPU found!")
            tot = round(psutil.virtual_memory()[1] / 1024 ** 2)
        total_cpu_mem = math.floor(psutil.virtual_memory().total / (1024 * 1024))
        print(f"RAM: {psutil.virtual_memory()[1] / 1024 ** 2:.0f}/{total_cpu_mem} MiB")
        print(f"Tot Av: ~{tot / 1024:.2f} GiB")

        import numpy as np
        import time

        matrix_size = 5000
        matrix_a = np.random.rand(matrix_size, matrix_size)
        matrix_b = np.random.rand(matrix_size, matrix_size)
        start_time = time.time()
        result_matrix = np.dot(matrix_a, matrix_b)
        end_time = time.time()
        elapsed_time = end_time - start_time
        print(f"Rough CPU comp ability: {matrix_size ** 3 / (elapsed_time * 1e9):.2f} GFLOPS")

    if python_version[0] != '3':
        warnings.warn("Python 2 is not supported!")
    if int(python_version[1]) < 10:
        warnings.warn("Python version lower than recommended (> 3.10.X).")
    if int(python_version[1]) < 4:
        warnings.warn("Python versions < 3.4 will not work!")
