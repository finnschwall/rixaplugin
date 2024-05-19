# Now we will do a more realistic example.
# You will first need to start this file and then 2_2_run_client.py
from rixaplugin import init_plugin_system, PluginModeFlags as PMF, create_and_start_plugin_server
from rixaplugin import get_functions_info

# Now we import some more "real" plugins
from rixaplugin.test import introspection
# This one adds a help() function that can be used e.g. in the LLM interface

from rixaplugin.default_plugins import math
# And here we just add some basic math functions
import asyncio

async def async_main():
    init_plugin_system(PMF.SERVER | PMF.THREAD, debug=True)
    # Now we add the SERVER flag.

    # We can now look if all functions have been loaded correctly
    print(get_functions_info())

    server, server_future = await create_and_start_plugin_server(port=7000, use_auth=True)
    # Time to start the plugin server. Again you could skip all of this using the CLI but it is more flexible this way
    # The server object is usually just for debugging of the networking system.

    # That's it so far.
    # Everything fine? Then let's move over to 2_2_run_client.py

    # This future will block indefinitely. It is used to keep the server running.
    await server_future


asyncio.run(async_main())