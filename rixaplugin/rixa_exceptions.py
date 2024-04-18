class FunctionNotFoundException(Exception):
    def __init__(self, function_name, message="Function not found"):
        self.function_name = function_name
        self.message = f"{message}: {function_name}"
        super().__init__(self.message)


class PluginNotFoundException(Exception):
    def __init__(self, plugin_name, message="Plugin not found"):
        self.plugin_name = plugin_name
        self.message = f"{message}: {plugin_name}"
        super().__init__(self.message)


class QueueOverflowException(Exception):
    def __init__(self, message="Queue overflow"):
        self.message = message
        super().__init__(self.message)