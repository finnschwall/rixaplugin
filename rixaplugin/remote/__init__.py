import types
from rixaplugin.internal.memory import _memory
"""
Remote plugins can be imported from here.

The modules are non-functional until the remote has connected.
"""


def __getattr__(name):
    module = types.ModuleType(name)  # EmptyModule(name)
    module.__file__ = f"{name}.py"
    module.__doc__ = f"Placeholder module for {name}. Not usable yet!"
    _memory.remote_dummy_modules[name] = module
    return module