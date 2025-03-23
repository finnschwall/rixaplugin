from rixaplugin.data_structures.enums import Scope
from rixaplugin.settings import config as _config
from rixaplugin.internal import api as internal_api
import inspect
from rixaplugin.internal.memory import _memory
import logging

variable_log = logging.getLogger("rixa.variables")


class PluginVariable:
    def __init__(self, name: str, var_type=str, default=None, options: list = None, user_facing_name: str = None,
                 readable: Scope = Scope.LOCAL, writable: Scope = Scope.LOCAL, custom_cast = None, description: str = None):
        """
        Define a variable that is controlled by the plugin system.

        Variables can be retrieved by using VARIABLE_NAME.get() and set by using VARIABLE_NAME.set(value)
        The value is defined by the config file, the admin interface or the user from which the current call originates.

        :param name: Name as used in config files or storage
        :param var_type: Data type of the variable. Usage of non-primitive types can cause serialization issues
        :param default: Default value of the variable
        :param options: List of possible values for the variable. Used for frontend dropdowns
        :param readable: Who gets read access. Also controls if sent over network
        :param writable: Who gets write access. WARNING: Users input will not be validated. Hence always check when not using options.
        :param custom_cast: Custom function to cast the values. Takes one argument (raw string from .ini file) and must return var_type(s)
        """
        self.name = name
        if custom_cast:
            self.default = _config(name, default=default, cast=custom_cast)
        else:
            self.default = _config(name, default=default, cast=var_type)
        self._value = self.default
        self.readable = readable
        self.user_facing_name = user_facing_name if user_facing_name else name
        self.writable = writable
        self.var_type = var_type
        self.options = options
        self.description = description
        stack = inspect.stack()
        self._plugin_name = stack[1].filename.split("/")[-1].split(".")[0]
        _memory.add_variable(self)

    def to_dict(self):
        return {
            "name": self.name,
            "type": self.var_type.__name__,
            "default": self.default,
            "value": self.get(),
            "user_facing_name": self.user_facing_name,
            "options": self.options,
            "readable": self.readable,
            "writable": self.writable
        }

    @staticmethod
    def from_dict(data):
        temp_var = PluginVariable(data["name"], data["type"], data["default"], data["options"],
                                  data["public_facing_name"], data["readable"], data["writable"])
        temp_var._value = data["value"]
        temp_var._plugin_name = data["plugin_name"]
        return temp_var

    def get(self):
        if self.writable == Scope.LOCAL:
            return self._value
        else:
            val = internal_api._plugin_ctx.get().plugin_variables.get(self._plugin_name, {}).get(self.name)
            if val is None:
                return self._value
            # check if type is actually correct
            if not isinstance(val, self.var_type):
                variable_log.error(f"Variable {self.name} in plugin {self._plugin_name} has incorrect type")
                return self._value
            return val

    def set(self, value):
        self._value = value
