import importlib
import types
import inspect
import sys

# def remote_plugin_to_module(plugin_dict):
#     plugin_name = plugin_dict['name']
#     plugin_functions = plugin_dict['functions']
#     autodoc = f"""Auto-generated module for RPC remote plugin: {plugin_name}
#     Available metadata: ID-{plugin_dict['id']}, Type-{plugin_dict['type']}"""
#     description = plugin_dict.get('description', autodoc)
#     module = create_module(plugin_name, plugin_functions, description=description)
#     sys.modules["rixaplugin.remote."+plugin_name] = module


def base_function_factory(*args, **kwargs):
    print("ORIG_FACTORY", args, kwargs)


def construct_importable(name, function_specs, description=None):
    module = create_module(name, function_specs, description)
    sys.modules[name] = module


def create_module(name, function_specs, description=None, module_file="REMOTE", function_factory=base_function_factory,
                  module=None):
    if not module:
        module = types.ModuleType(name)
        module.__file__ = module_file
        setattr(module, "__file__", "REMOTE")
    module.__doc__ = "Auto-generated module for RPC remote plugin: " + name if not description else description



    for func_spec in function_specs:
        func_name = func_spec['name']
        args = func_spec.get('args', [])
        kwargs = func_spec.get('kwargs', [])
        varkw = func_spec.get('varkw', None)
        docstring = func_spec.get('doc', '')
        proxy_function = create_function_with_signature(func_name, args, kwargs, varkw, docstring, function_factory=function_factory)
        setattr(module, func_name, proxy_function)

    return module



def create_function_with_signature(name, args, kwargs, varkw, return_annotation=None, docstring="",
                                   function_factory=base_function_factory):
    parameters = []
    for arg in args:
        parameters.append(inspect.Parameter(
            name=arg['name'],
            kind=arg["kind"],#inspect.Parameter.POSITIONAL_OR_KEYWORD,
            annotation=arg.get('type', inspect.Parameter.empty),
            default=inspect.Parameter.empty
        ))

    for kwarg in kwargs:
        default = kwarg.get('default', inspect.Parameter.empty)
        parameters.append(inspect.Parameter(
            name=kwarg['name'],
            kind=kwarg["kind"], #inspect.Parameter.KEYWORD_ONLY,
            annotation=kwarg.get('type', inspect.Parameter.empty),
            default=default #if default is not None else inspect.Parameter.empty
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
        return function_factory(name, bound.args, bound.kwargs)

    func.__signature__ = sig
    func.__name__ = name
    func.__doc__ = docstring
    func.__annotations__ = {k: v.annotation for k, v in sig.parameters.items()}
    if return_annotation is not None:
        func.__annotations__['return'] = return_annotation

    return func
