import base64
import os

import sympy
import plotly.express as px
from rixaplugin.decorators import plugfunc
import rixaplugin.sync_api as api
from sympy import latex, lambdify
import numpy as np
import subprocess as sp
import plotly.graph_objects as go
from rixaplugin import variables as var


latex_available = var.PluginVariable("LATEX_AVAILABLE", bool,default=False, readable=var.Scope.USER)

@plugfunc()
def draw_feynman(feynman):
    """
    Draw a feynman diagram using tikz-feynman

    Pay special attention with the argument. Use triple quotes with r prefix to avoid escaping issues.
    This method does not raise any exceptions when the diagram is not valid.

    Example:
    Electron-positron to muon-antimuon via photon
    draw_feynman(r'''\feynmandiagram [horizontal=a to b] {
  i1 [particle=\(e^{-}\)] -- [fermion] a -- [fermion] i2 [particle=\(e^{+}\)],
  a -- [photon, edge label=\(\gamma\), momentum'=\(k\)] b,
  f1 [particle=\(\mu^{+}\)] -- [fermion] b -- [fermion] f2 [particle=\(\mu^{-}\)],
};''')
    :param feynman: feynman-tikz code as a string
    :return: This function immediately displays the diagram
    """
    latex_start = r"""\documentclass[convert={density=300,size=600x400,outext=.png}]{standalone}
\usepackage{tikz-feynman}
\begin{document}
"""
    latex_end = """
\end{document}"""
    if not r"\feynmandiagram" in feynman and "feynmandiagram" in feynman:
        feynman = feynman.replace("feynmandiagram", r"\feynmandiagram")

    latex_total = latex_start + feynman + latex_end
    id = str(hash(latex_total))

    if not latex_available.get():
        api.display(html=f"<h3>NO LATEX COMPILER AVAILABLE</h3><code>{feynman}</code>")
        return

    try:
        with open(f"tmp/temp.tex", "w") as f:
            f.write(latex_total)
        sp.call(["lualatex", "-shell-escape", "-interaction=nonstopmode", f"temp.tex"], cwd="tmp", stdout=sp.DEVNULL, stderr=sp.DEVNULL)
        with open(f"tmp/temp.png", "rb") as f:
            img_base64 = base64.b64encode(f.read()).decode()
            print("displaying")
            api.display(html=f'<img src="data:image/png;base64,{img_base64}" style="background-color:white;height:100%; width:auto"/>')
    except Exception as e:
        print(e)
        api.display(html=f"<h3>ERROR IN DRAWING DIAGRAM</h3><code>{feynman}</code>")
        # api.display(html=f.read())

@plugfunc()
def draw_plot_3D(function, xstart=-5, xend=5, ystart=-5,yend=5):
    """
    Draw a 3D plot of a function

    Example: draw_plot_3D("x**2+y**2")
    Same rules as for draw_plot apply here!
    :return:
    """
    if not function:
        api.display_message("No function supplied", 5, "danger")
        return
    expr = sympy.sympify(function)
    res = 50
    res = res * 1j
    lambd_expr = sympy.lambdify(list(expr.free_symbols), expr)
    x, y = np.mgrid[xstart:xend:res, ystart:yend:res]
    z = lambd_expr(x, y)
    fig = go.Figure(data=[go.Surface(x=x, y=y, z=z)])
    api.display(html=fig.to_html(include_plotlyjs=False, full_html=False))



@plugfunc()
def draw_plot(function, x_range_start=-10, x_range_end=10):
    """
    Draw a plot of a function that depends on x

    Example: draw_plot("x**2+3", -10, 10)
    Variables other than x will not be recognized.
    This uses sympy. So keep in mind that the function must be a valid sympy expression.
    I.e. e^x would exp(x).
    Stuff like "1/x if x != 0 else 0" is not supported as it is not a valid sympy expression.
    :param function: Function as a string. x is the name of the main variable
    :param x_range_start:
    :param x_range_end:
    :return: Displays the plot
    """
    # from rixaplugin.data_structures import rixa_exceptions
    # raise rixa_exceptions.RemoteOfflineException("Plugin 'math' is currently unreachable")
    if "x" not in function:
        raise ValueError("Function must contain x as the main variable")
    x = sympy.symbols('x')
    y = sympy.sympify(function)
    x_vals = list(np.linspace(x_range_start, x_range_end, 200))
    # use lambdify to generate y values

    func = lambdify(x, y)
    y_vals = [func(val) for val in x_vals]
    fig = px.line(x=x_vals, y=y_vals)
    api.display(html=fig.to_html(include_plotlyjs=False, full_html=False))


@plugfunc()
def latexify(expression):
    """
    Convert an expression to latex

    Latex will be automatically rendered in the output. Preferable over strings
    Example: latexify("x**2+3") to convert x^2+3 to latex.
    :param expression: Expression as a string
    :return: Latex string
    """
    return latex(sympy.sympify(expression))


@plugfunc()
def solve_equation(equation):
    """
    Solve an equation of the form f(x)=0

    Example: solve_equation("x**2-4") to solve x^2=4
    :param equation: Equation as a string
    :return: Solution as a list
    """
    x = sympy.symbols('x')
    eq = sympy.sympify(equation)
    sol = sympy.solve(eq, x)
    return sol


@plugfunc()
def differentiate(function):
    """
    Differentiate a function

    Example: differentiate("x**2+3") to differentiate x^2+3
    :param function: Function as a string
    :return: Derivative as a latex string
    """
    x = sympy.symbols('x')
    y = sympy.sympify(function)
    dy_dx = sympy.diff(y, x)
    return str(dy_dx)


@plugfunc()
def integrate(function):
    """
    Integrate a function

    Example: integrate("x**2+3") to integrate x^2+3
    :param function: Function as a string
    :return: Integral as a latex string
    """
    x = sympy.symbols('x')
    y = sympy.sympify(function)
    integral = sympy.integrate(y, x)
    return str(integral)


@plugfunc()
def simplify_expression(expression):
    """
    Simplify an expression

    Example: simplify_expression("x**2+2*x+1") to simplify x^2+2x+1
    :param expression: Expression as a string
    :return: Simplified expression as a latex string
    """
    x = sympy.symbols('x')
    expr = sympy.sympify(expression)
    simplified = sympy.simplify(expr)
    return str(simplified)


@plugfunc()
def evaluate(expression):
    """
    Evaluate an expression

    Example: evaluate("2^4+1") returns 17
    :param expression:
    :return: Expression or number
    """
    return str(sympy.sympify(expression))

# @plugfunc()
# def calculate_limit(function, x_val, direction="both"):
#     """
#     Calculate the limit of a function at a given point
#
#     Example: calculate_limit("1/x", 0) to calculate the limit of 1/x at x=0
#     :param function: Function as a string
#     :param x_val: Value of x
#     :param direction: "both", "left" or "right"
#     :return: Limit as a latex string
#     """
#     x = sympy.symbols('x')
#     y = sympy.sympify(function)
#     if direction == "both":
#         limit = sympy.limit(y, x, x_val)
#     elif direction == "left":
#         limit = sympy.limit(y, x, x_val, dir='-')
#     elif direction == "right":
#         limit = sympy.limit(y, x, x_val, dir='+')
#     return limit
#
#
# @plugfunc()
# def taylor(series, x0, n):
#     """
#     Calculate the Taylor series of a function
#
#     Example: taylor("sin(x)", 0, 5) to calculate the Taylor series of sin(x) at x=0 up to the 5th term
#     :param series: Function as a string
#     :param x0: Point of expansion
#     :param n: Number of terms
#     :return: Taylor series object
#     """
#     x = sympy.symbols('x')
#     y = sympy.sympify(series)
#     taylor_series = sympy.series(y, x, x0, n).removeO()
#     return taylor_series
