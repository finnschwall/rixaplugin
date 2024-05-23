import inspect
from _ast import AST

from docstring_parser import parse
import ast

from rixaplugin.data_structures.rixa_exceptions import SignatureMismatchException, FunctionNotFoundException


def class_to_func_signatures(cls):
    # Turn all public methods of a class into function signatures
    function_specs = []
    for name, method in inspect.getmembers(cls, predicate=inspect.isfunction):
        if name.startswith('_'):
            continue
        function_specs.append(function_signature_to_dict(method))
    return function_specs

def generate_python_doc(func_dict, include_docstr=True, short=False, tabulators=1):
    func_name = func_dict.get('name', "UNKNOWN")
    args = func_dict.get('args', [])
    kwargs = func_dict.get('kwargs', [])
    doc = f"def {func_name}("
    for arg in args:
        arg_type = ""
        if "type" in arg:
            arg_type = ":" + arg["type"]
        doc += f"{arg['name']}" + arg_type + ", "
    for kwarg in kwargs:
        kwarg_type = ""
        if "type" in kwarg:
            kwarg_type = ":" + kwarg["type"]
        doc += f"{kwarg['name']}{kwarg_type}={kwarg.get('default', 'None')}, "
    doc = doc.rstrip(', ') + ")"

    if include_docstr:
        docstr = ""
        if "description" in func_dict and func_dict["description"] is not None and func_dict["description"] != "":
            docstr += ""+ func_dict["description"] + "\n"
            if "long_description" in func_dict and func_dict["long_description"] is not None and func_dict["long_description"] != "" and not short:
                docstr += "\n" + func_dict["long_description"] + "\n"
        if not short:
            for arg in args:
                if "description" in arg:
                    docstr += f":param {arg['name']}: {arg.get('description', '')}\n"
            for kwarg in kwargs:
                docstr += f":param {kwarg['name']}: {kwarg.get('description', '')}\n"
        if "return" in func_dict and func_dict["return"] is not None and func_dict["return"] != "" and not short:
            docstr += ":return: " + func_dict["return"]
        if docstr != "":
            docstr = '\n"""\n' + docstr + '"""'
            docstr = docstr.split("\n")
            tabs = "\t" * tabulators
            docstr = "\n".join([f"{tabs}{line}" for line in docstr])
            doc += docstr
    return doc


def function_signature_to_dict(func):
    sig = inspect.signature(func)
    params = sig.parameters

    doc = parse(func.__doc__)

    args = []
    kwargs = []
    has_var_positional = False  # Flag for *args
    has_var_keyword = False  # Flag for **kwargs

    for name, param in params.items():
        if param.kind == inspect.Parameter.VAR_POSITIONAL:
            has_var_positional = True
        elif param.kind == inspect.Parameter.VAR_KEYWORD:
            has_var_keyword = True
        elif param.default == inspect.Parameter.empty:
            arg = {'name': name, "kind": param.kind}
            for doc_param in doc.params:
                if doc_param.arg_name == name:
                    if doc_param.type_name:
                        arg['type'] = doc_param.type_name
                    else:
                        if param.annotation != inspect.Parameter.empty:
                            arg['type'] = param.annotation.__name__
                    if doc_param.description and doc_param.description != "":
                        arg['description'] = doc_param.description
            args.append(arg)
        else:
            kwarg = {'name': name, 'default': param.default, "kind": param.kind}
            for doc_param in doc.params:
                if doc_param.arg_name == name:
                    kwarg_type = doc_param.type_name
                    if not kwarg_type:
                        if param.annotation != inspect.Parameter.empty:
                            kwarg_type = param.annotation.__name__
                        # if param.default:
                            # kwarg_type = type(param.default).__name__
                    if kwarg_type:
                        kwarg['type'] = kwarg_type
                    if doc_param.description and doc_param.description != "":
                        kwarg['description'] = doc_param.description
            kwargs.append(kwarg)
    # print(func.__name__, kwargs)
    return {
        'name': func.__name__,
        'description': doc.short_description,
        'long_description': doc.long_description,
        'return': doc.returns.description if doc.returns else None,
        'args': args,
        'kwargs': kwargs,
        'has_var_positional': has_var_positional,
        'has_var_keyword': has_var_keyword
    }



class CodeVisitor(ast.NodeVisitor):
    def __init__(self, func_callback, func_map={}):
        self.func_map = func_map

        self.func_callback = func_callback
        self.variables = {}
        self.collection = []
        self.least_one_call = False

    async def visit_Call(self, node):
        func_name = node.func.id
        args = []
        for arg in node.args:
            if isinstance(arg, ast.Name):
                if arg.id in self.variables:
                    args.append(self.variables.get(arg.id))
                else:
                    raise Exception(f"Variable with name '{arg.id}' not found")
            else:
                args.append(ast.literal_eval(arg))
        kwargs = {kw.arg: self.variables.get(kw.value.id, None) if isinstance(kw.value, ast.Name) else ast.literal_eval(
            kw.value) for kw in node.keywords}

        resolved_func = None
        for func in self.func_map:
            if func["name"] == func_name:
                resolved_func = func
                break

        if not resolved_func:
            raise FunctionNotFoundException(f"'{func_name}' not found")
        # TODO fix this. Really doesnt help as of now
        # self.check_signature_compatibility(node, resolved_func)

        if resolved_func:
            result = await self.func_callback(resolved_func, args, kwargs)#resolved_func["pointer"](*args, **kwargs)
            self.least_one_call = True
            self.variables['__call_res__'] = result
            return result
        else:
            return f"Function {func_name} not found"

    def check_signature_compatibility(self, node, function_metadata):
        # Extract the argument names from the metadata
        expected_arg_names = [arg['name'] for arg in function_metadata['args']]
        # Check if the number of positional arguments in the node matches the expected number
        if len(node.args) > len(expected_arg_names) + len(function_metadata["kwargs"]) and not function_metadata['has_var_positional']:
            raise SignatureMismatchException(f"Too many positional arguments for function '{function_metadata['name']}'"
                                             f"Correct signature is: '{generate_python_doc(function_metadata)[4:]}'")
        # Check if all keyword arguments in the node are expected
        if not function_metadata['has_var_keyword']:
            for kw in node.keywords:
                if kw.arg not in expected_arg_names:
                    raise SignatureMismatchException(f"Unexpected keyword argument '{kw.arg}' for function '{function_metadata['name']}'"
                                                     f"Correct signature is: '{generate_python_doc(function_metadata)[4:]}'")
        return True

    async def resolve_arg(self, arg):
        if isinstance(arg, ast.Name):
            return self.variables.get(arg.id)
        else:
            return ast.literal_eval(arg)

    async def visit_Assign(self, node):
        if isinstance(node.targets[0], ast.Name):
            var_name = node.targets[0].id
            if isinstance(node.value, ast.Call):
                value = await self.visit(node.value)
            elif isinstance(node.value, ast.Name):
                value = self.variables.get(node.value.id)
            else:
                value = ast.literal_eval(node.value)

            self.variables[var_name] = value

    async def visit(self, node):
        """Visit a node."""
        method = 'visit_' + node.__class__.__name__
        visitor = getattr(self, method, self.generic_visit)
        return await visitor(node)

    async def generic_visit(self, node):
        """Called if no explicit visitor function exists for a node."""
        for field, value in ast.iter_fields(node):
            if isinstance(value, list):
                for item in value:
                    if isinstance(item, AST):
                        await self.visit(item)
            elif isinstance(value, AST):
               await self.visit(value)