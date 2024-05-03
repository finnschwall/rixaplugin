from rixaplugin import init_plugin_system, PluginModeFlags as PMF, create_and_start_plugin_client
from rixaplugin import async_execute, async_execute_code, get_state_info, get_function_entry, get_functions_info

import asyncio

# Notice how we did not import any plugins? We will now fetch our plugins from the remote
async def async_main():
    init_plugin_system(PMF.CLIENT | PMF.THREAD, debug=True)
    # Now we are in client mode.
    # Note that client and server mode are NOT exclusive. You can do one server and many clients.

    # Lets see how many functions we have
    print(get_functions_info())
    # Looks like none? Let's change that
    client, client_future = await create_and_start_plugin_client("localhost", 7000, return_future=True)
    # This will connect to the server we started in 2_1_run_server.py
    # And you should see a log message indicating success
    await asyncio.sleep(2)
    # Just to give some time to read the log messages

    # Now let's take another look at the functions
    print(get_functions_info())
    # Now we should see functions from the server
    # But oh wait. The help() function we imported on the server is missing. The solution for that can be found in the plugin definition
    # (It's marked as local only i.e. will never be sent)

    # But we do have the math functions. So let's do some remote integration

    future = await async_execute("integrate", args=["x^2"], return_future=True)
    return_value = await future
    print("Return", return_value)

    # We can also do code execution
    code = """var = integrate("x^2")
integrate(var)"""
    future = await async_execute_code(code, return_future=True)
    return_value = await future
    print("Return from code", return_value)

    # That's the most important stuff.
    # You can also connect to multiple servers or start a server and then connect to clients, etc...


asyncio.run(async_main())
