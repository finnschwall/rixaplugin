from rixaplugin.data_structures.enums import Scope
from rixaplugin.settings import config as _config

class PluginVariable:
    def __init__(self, name: str, var_type=str, default=None, readable=Scope.LOCAL, writable=Scope.LOCAL):
        self.name = name
        self.default = default
        self.value = _config(name, default=default, cast=var_type)#default_value
        self.readable = readable
        self.writable = writable
        self.var_type = var_type


    def get(self):
        return self.value

    def set(self, value):
        self.value = value
