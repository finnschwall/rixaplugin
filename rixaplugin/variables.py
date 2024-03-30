from .enums import Scope


class PluginVariable:
    def __init__(self, name: str, var_type=str, default_value=None, readable=Scope.LOCAL, writable=Scope.LOCAL):
        self.name = name
        self.default_value = default_value
        self.value = default_value
        self.readable = readable
        self.writable = writable

    def get(self):
        return self.value

    def set(self, value):
        self.value = value
