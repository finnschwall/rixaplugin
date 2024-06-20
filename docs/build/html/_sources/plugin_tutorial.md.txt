# Plugin programming quickstart

## Prerequisites

Install rixaplugin and make sure it works via
```bash
rixaplugin setup get-system-info
```
Go to a folder where you want to work on the project. Now setup a new plugin project via
```bash
rixaplugin setup setup-work-dir
```

## Basics
There are two ways to write a plugin (in python):
Async and sync.

If you don't know what async is, use the sync version and skip to the next section.

### Async
All methods shown in the tutorial exist in an async version. Most of the tutorial is also applicable.
There are 3 reasons to use async:
1. High throughput. However this only applies if you really know what you are doing
2. Direct interaction with the plugin system
3. You need to do something that is not covered by the default sync implementation

If none of these apply to you, use the sync version.

To get started with async look at the async [tutorial](https://github.com/finnschwall/rixaplugin/tree/main/examples/tutorial).
For direct interaction with the plugin system or programming of cases that is not covered by the default sync implementation,
look at the rixaplugin.internal docs.


### Sync
You basically program like you would any other python program.
Avoid functions that have `async_` in their name. They will produce confusing errors.


## Writing a plugin

### The basics
There are key aspects to writing a plugin:
1. The plugin system is purely functional

Your functions are grouped by the file they are in but ultimately they are just functions.
No classes, no modules, no shared variables.
2. The plugin system is stateless

This is crucial! Even if a user interaction leads to two calls inside your plugin, they are not connected.
Your plugin is (for the most part) unaware where the call even came from.
If you work in the sync version this is even more important. The same variable inside your plugin is potentially different for two functions.
If you need to store data or make data available across functions use `PluginVariable` from `rixaplugin.variable`
3. Docstrings and typehints are not optional

The main server that executes your plugin functions relies on knowing what exactly your functions do.
If you don't provide __good__ docstrings and correct typehints, your plugin will not work as intended.
4. Proper exceptions

Make sure that your functions raise understandable exceptions.
This does not mean you need a manual exception for every possible error.
But if an error is raised, the next course of action should be clear from the exception message.
Especially in cases where an error is potentially recoverable, a verbose exception can make a huge difference.

### Examples
Before you continue look at the various [default plugins](https://github.com/finnschwall/rixaplugin/tree/main/rixaplugin/default_plugins).
math and catbot are the most straightforward. They should provide a good reference for your own plugin.

### Coding
The most important part:
You always start without the plugin system.
Be sure that all of your functions work as intended.
Debugging inside the plugin system is cumbersome and is for unexpected errors only.

### Everything ready?
* Do all your functions work?
* Is everything documented?
* Are your functions stateless?
* How do your functions react to faulty input?
* Are your functions tested?
* Are there exceptions?
* Have you set up logging or print statements for debugging?

### Running the plugin

Start with a dryrun
```bash
rixaplugin start-client YOUR_FILE.py
```
inside your plugin directory.

Everything works? Great. Stop the server. You are ready for a proper setup.

Inside your working directory should be a `config.ini` file.
This file is used to configure your plugin. E.g. you'll need to change `PLUGIN_DEFAULT_PORT` when you want to connect to a server.
All settings are documented in the [docs](https://finnschwall.github.io/rixaplugin/modules/rixaplugin.html#module-rixaplugin.settings).

If you want to connect to a RIXA server instance, follow this [tutorial](https://finnschwall.github.io/rixaplugin/auth_system.html)


