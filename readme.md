<img src="https://cdn-icons-png.flaticon.com/512/6261/6261561.png" alt="drawing" width="75"/>
<b>You are entering an active construction zone!</b>


# RIXA Plugin System

Welcome to RIXA's plugin system documentation!

## Features

Check out [RIXA](https://github.com/finnschwall/RIXA/tree/main) or [PyALM](https://github.com/finnschwall/PyALM)
or both.

You can extend functionality either for the webserver or an LLM using this.

Alternatively this can be used to connect to any RIXAplugin.

## Installation
```
pip3 install git+https://github.com/finnschwall/rixaplugin
```

## Getting Started

### Tutorial

see [tutorial](https://github.com/finnschwall/rixaplugin/tree/main/examples/tutorial)

### Configuring a plugin
Create a `config.ini` in the same folder. For more infos see the settings section in the [docs](https://finnschwall.github.io/rixaplugin/).


### Running or connecting a plugin
Run a plugin file via the rixaplugin command line tool.

#### As server
Runs the plugin as a server. Allows connections from other plugins.
```bash
rixaplugin start_as_server path/to/plugin.py
```

#### As client
Runs the plugin as a client. Connects to a server.
```bash
rixaplugin start_as_client path/to/plugin.py ADDRESS PORT
```

#### Advanced
Use `create_and_start_plugin_server` and `create_and_start_plugin_client` for advanced use cases.
This also allows for hybrid server/client plugins. Be advised that a plugin can only run 1 server.
However there is no limit to the amount of servers a client can connect to.


## Documentation

[DOCS](https://finnschwall.github.io/rixaplugin/)
