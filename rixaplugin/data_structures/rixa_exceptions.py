class FunctionNotFoundException(Exception):
    def __init__(self, message="Function not found"):
        # self.function_name = function_name
        self.message = message
        # self.message = f"{message}: {function_name}"
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

class SignatureMismatchException(Exception):
    def __init__(self, message="Signature mismatch"):
        self.message = message
        super().__init__(self.message)

class NoEffectException(Exception):
    def __init__(self, message="Valid statement but no effect"):
        self.message = message
        super().__init__(self.message)


class RemoteException(Exception):
    def __init__(self, type, message, traceback):
        self.type = type
        self.original_message = message
        self.traceback = traceback
        super().__init__(f"{type}: {message}\nRemote traceback:\n{traceback}")


class RemoteTimeoutException(Exception):
    def __init__(self, message="Remote time out"):
        self.message = message
        super().__init__(self.message)