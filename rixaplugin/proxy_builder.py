import types
import inspect
from functools import wraps
import sys


def rpc_call(*args, **kwargs):
    print(args, kwargs)


function_factory = rpc_call


def construct_importable(name, function_specs, description=None):
    module = create_module(name, function_specs, description)
    sys.modules[name] = module


def create_module(name, function_specs, description=None, module_file="REMOTE"):
    module = types.ModuleType(name)
    module.__doc__ = "Auto-generated module for RPC remote plugin: " + name if not description else description

    module.__file__ = module_file

    setattr(module, "__file__", "REMOTE")

    for func_spec in function_specs:
        func_name = func_spec['name']
        args = func_spec.get('args', [])
        kwargs = func_spec.get('kwargs', [])
        varkw = func_spec.get('varkw', None)
        docstring = func_spec.get('doc', '')
        proxy_function = create_function_with_signature(func_name, args, kwargs, varkw, docstring)
        setattr(module, func_name, proxy_function)

    return module


def create_function_with_signature(name, args, kwargs, varkw, return_annotation=None, docstring=""):
    parameters = []
    for arg in args:
        parameters.append(inspect.Parameter(
            name=arg['name'],
            kind=inspect.Parameter.POSITIONAL_OR_KEYWORD,
            annotation=arg.get('type', inspect.Parameter.empty),
            default=inspect.Parameter.empty
        ))

    for kwarg in kwargs:
        default = kwarg.get('default', inspect.Parameter.empty)
        parameters.append(inspect.Parameter(
            name=kwarg['name'],
            kind=inspect.Parameter.KEYWORD_ONLY,
            annotation=kwarg.get('type', inspect.Parameter.empty),
            default=default if default is not None else inspect.Parameter.empty
        ))

    if varkw:
        parameters.append(inspect.Parameter(
            name=varkw['name'],
            kind=inspect.Parameter.VAR_KEYWORD
        ))

    sig = inspect.Signature(parameters, return_annotation=return_annotation)

    def func(*args, **kwargs):
        bound = sig.bind(*args, **kwargs)
        bound.apply_defaults()
        return function_factory(name, args=bound.args, kwargs=bound.kwargs)

    func.__signature__ = sig
    func.__name__ = name
    func.__doc__ = docstring
    func.__annotations__ = {k: v.annotation for k, v in sig.parameters.items()}
    if return_annotation is not None:
        func.__annotations__['return'] = return_annotation

    return func


# def function_signature_from_spec(func_spec):
#     """
#     Generates a string representation of a function signature from a dictionary specification.
#
#     :param func_spec: A dictionary containing the function specification. Expected keys are 'name', 'args', 'kwargs', and 'varkw'.
#     :return: A string representing the function signature.
#     """
#     func_name = func_spec['name']
#     args = func_spec.get('args', [])
#     kwargs = func_spec.get('kwargs', [])
#     varkw = func_spec.get('varkw')
#
#     # Constructing the positional arguments part
#     args_str = ", ".join(args)
#
#     # Constructing the keyword arguments part
#     kwargs_str = ", ".join([f"{kwarg}={kwarg}" for kwarg in kwargs])
#
#     # Combining args and kwargs parts
#     signature_parts = [part for part in [args_str, kwargs_str] if part]
#     signature = ", ".join(signature_parts)
#
#     # Adding **kwargs if varkw is specified
#     if varkw:
#         signature += ", **" + varkw
#
#     # Constructing the full function signature
#     full_signature = f"def {func_name}({signature}):"
#
#     return full_signature


def __function_signature_from_spec(func_dict, include_docs=True, include_types=True):
    """
    Generates a string representation of a function based on the given dictionary.

    Parameters:
    - func_dict: Dictionary containing function details.
    - include_docs: Boolean indicating whether to include docstrings.
    - include_types: Boolean indicating whether to include type hints.

    Returns:
    - A string that represents the function.
    """
    func_name = func_dict['name']
    description = func_dict.get('description', '')
    args_list = func_dict['args']
    kwargs_list = func_dict['kwargs']
    has_var_positional = func_dict.get('has_var_positional', False)
    has_var_keyword = func_dict.get('has_var_keyword', False)

    # Constructing arguments and keyword arguments strings
    args_str = ", ".join(
        [f"{arg['name']}" + (f": {arg['type']}" if include_types and 'type' in arg else '') for arg in args_list])
    kwargs_str = ", ".join(
        [f"{kwarg['name']}={kwarg['default']}" + (f": {kwarg['type']}" if include_types and 'type' in kwarg else '') for
         kwarg in kwargs_list])

    # Adding *args and **kwargs if present
    if has_var_positional:
        args_str += ", *args" if args_str else "*args"
    if has_var_keyword:
        args_str += ", **kwargs" if args_str or has_var_positional else "**kwargs"

    # Combining all parts
    func_str = f"def {func_name}({args_str + (', ' + kwargs_str if kwargs_str else '')}):"

    # Adding docstring if required
    if include_docs and description:
        func_str += f"\n    \"\"\"{description}\"\"\""

    return func_str