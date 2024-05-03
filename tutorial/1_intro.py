# This will show how to use the most important features of the plugin system
# Let's begin with the easiest case: A simple function call

# We start by importing the plugin. In that case a test plugin
from rixaplugin.test import sync_test_plugin

# We know need to set up the plugin system itself.
# There are easier ways to do this, but this is the most flexible one.
# You could skip all of this e.g. with the CLI
# But this allows you full control and it's usually easier to debug

# Most of the important stuff is contained in rixaplugins main module
from rixaplugin import init_plugin_system, PluginModeFlags as PMF
from rixaplugin import async_execute, async_execute_code, get_state_info, get_function_entry, get_functions_info

# The plugin system runs entirely asynchronous. Hence some boilerplate code is required
# Again you could skip this e.g. by just executing your plugin file with
# rixaplugin start-as-client YOUR_FILE
# But for debugging I'd strongly recommend to do it this way

import asyncio
async def async_main():
    # We need this function because asyncio functions can't be called outside an async function
    # But now we can initialize the plugin system
    init_plugin_system(PMF.THREAD, debug=True)
    # Notice the flag. We are starting in thread mode.
    # Alternatively we could have started with PMF.PROCESS. One of the two is required.
    # It decides how plugin functions are executed.
    # Rule of thumb: You wait for a network result, a read file, a database query, etc. -> THREAD
    # You do heavy computation -> PROCESS

    # Now we can execute a function in the plugin system. Let's do an example function
    future = await async_execute("test_print", args=["Hello there!"], return_future=True)
    return_value = await future
    print("Returning:", return_value)
    # A lot is going on here so let's break it down:
    # async_execute is the function to execute plugin functions. For more detailed info use help(async_execute)

    print("-------")
    # Why make it so complicated? Why not do:
    # sync_test_plugin.test_print("Hello there!")
    # Mainly that actually won't work. The plugin system is designed to be highly parallel.
    # A demonstration for that
    future1 = await async_execute("test_delay", args=[1], return_future=True)
    future2 = await async_execute("test_delay", args=[2], return_future=True)
    print("Job1", await future1)
    print("Job2", await future2)
    # As you will see there will be only 1 seconds of delay, between the two print statements
    # The main takeaway here is that the future system allows for submitting many jobs independently
    # Usually you do not have to worry about that. The plugin system will take care of it for you
    # You can write plugins entirely in synchronous code (i.e. without the future shenanigans)
    # But for interacting with the plugin system you need to use async functions
    # Otherwise you would block the system. Not good if you are running a server

    # That so far has been sufficient to test any function on its own. But how would the LLM interface interact with your code?
    # It would use execute_code. Let's do an example
    print("-------")

    code = """var = test_return_single_value()
test_print(var)"""
    future = await async_execute_code(code, return_future=True)
    return_value = await future
    print("Returning from code:", return_value)

    # This is the most important part. If your code works like this, it will work in the LLM interface
    # But one puzzle piece is missing.
    # How does the LLM even know which function exist and how to call them?
    # That's where get_state_info and get_plugin_info come in
    print("-------")
    # get_state_info will print the most important stuff about its current state. That includes ALL plugins, remote or local
    print(get_state_info())


    # Now we saw all functions. But how about an individual one?
    print("-------")
    from pprint import pprint
    # We use prettyprint as the infos on a function can be quite extensive
    pprint(get_function_entry("test_signature_and_doc_compile"))


    print("-------")
    # And what does the LLM actually see? It is somewhat dependent on a config but usually it will look like this
    print(get_functions_info())
    # As you can see only one function is actually documented. So only one is really suitable for the LLM interface
    # As a rule of thumb: Think if you could use these functions without any other information. If not, then add information.
    # This part is crucial!


asyncio.run(async_main())
