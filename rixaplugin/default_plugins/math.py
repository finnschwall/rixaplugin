import base64
import os
import sys

import requests
import sympy
import plotly.express as px
from rixaplugin.decorators import plugfunc
import rixaplugin.sync_api as api
from sympy import latex, lambdify
import numpy as np
import subprocess as sp
import plotly.graph_objects as go
from rixaplugin import variables as var
import logging

latex_available = var.PluginVariable("LATEX_AVAILABLE", bool, default=False, readable=var.Scope.USER)
wolfram_appid = var.PluginVariable("WOLFRAM_APPID", str)


logger = logging.getLogger(__name__)


@plugfunc()
def query_wolfram_alpha(input_query: str):
    """
    Query the Wolfram|Alpha LLM API. Has the same functionality as wolfram alpha.

    This sends a natural language query and returns a text and possibly links to images of plots.
    Use this only for queries that are not covered by any of the other available functions (e.g do not plot x2 using this. Do not query for data that likely is included in the RAG db.)

    The wolfram api usually returns images, plots or similar in the form of links. Use the display function to show these.

    :param input_query: The natural language query to be processed by Wolfram|Alpha. This should be a single-line string, simplified to
                        keywords whenever possible (e.g., "France population" instead of "How many people live in France?").
    :type input_query: str

    :param maxchars: The maximum number of characters to return in the response. Default is 6800. Use this to limit the response size.
    :type maxchars: int, optional
^
    :returns: text

    :raises HTTP 501: The input could not be interpreted. Check for misspellings or formatting issues.
    :raises HTTP 400: The input parameter is missing or incorrect.

    :Example Usage:

    >>> query_wolfram_alpha("10 densest elemental metals", maxchars=500)
    """
    maxchars: int = 6800
    appid = wolfram_appid.get()

    base_url = "https://www.wolframalpha.com/api/v1/llm-api"

    # Prepare the query parameters
    params = {
        "appid": appid,
        "input": input_query,
        "maxchars": maxchars,
    }

    response = requests.get(base_url, params=params)

    if response.status_code == 501:
        raise ValueError(f"Wolfram|Alpha could not interpret the input. Suggested inputs: {response.text}")
    elif response.status_code == 400:
        raise ValueError("Missing or incorrect input parameter. Check your query syntax.")
    elif response.status_code == 403:
        if "Invalid appid" in response.text:
            raise ValueError("Invalid AppID. Check your AppID and try again.")
        elif "Appid missing" in response.text:
            raise ValueError("No AppID provided. Include your AppID in the request.")
    elif response.status_code != 200:
        raise ValueError(f"Unexpected error: {response.status_code} - {response.text}")

    return response.text



@plugfunc()
def draw_feynman(feynman):
    """
    Draw a feynman diagram using tikz-feynman

    Pay special attention with the argument. Use triple quotes with r prefix to avoid escaping issues.
    This method does not raise any exceptions when the diagram is not valid.

    This only displays the diagram. It does not return anything.

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
    if r"\begin{feynman}" in feynman:
        if not r"\begin{tikzpicture}" in feynman:
            feynman = feynman.replace(r"\begin{feynman}", r"\begin{tikzpicture}\begin{feynman}")
            feynman = feynman.replace(r"\end{feynman}", r"\end{feynman}\end{tikzpicture}")


    latex_total = latex_start + feynman + latex_end
    id = str(hash(latex_total))

    if not latex_available.get():
        api.display(html=f"<h3>NO LATEX COMPILER AVAILABLE</h3><code>{feynman}</code>")
        return

    try:
        import os
        if not os.path.exists("/tmp/rixa_tex"):
            os.makedirs("/tmp/rixa_tex")
        with open(f"/tmp/rixa_tex/temp.tex", "w") as f:
            f.write(latex_total)
        # sp.call(["lualatex", "-shell-escape", "-interaction=errorstopmode", f"/tmp/rixa_tex/temp.tex"], cwd="/tmp/rixa_tex", stdout=sp.DEVNULL, stderr=sp.DEVNULL)
        result = sp.run(
            [
                "lualatex",
                #"-shell-escape",
                "-halt-on-error",  # Stop on first error
                "-interaction=nonstopmode",
                "-file-line-error",  # Show file and line for errors
                f"/tmp/rixa_tex/temp.tex"
            ],
            cwd="/tmp/rixa_tex",
            capture_output=True,
            text=True,
            check=True
        )
        with open(f"/tmp/rixa_tex/temp.png", "rb") as f:
            img_base64 = base64.b64encode(f.read()).decode()
            api.display(html=f'<img src="data:image/png;base64,{img_base64}" style="background-color:white;height:100%; width:auto"/>')
    except sp.CalledProcessError as e:
        with open(f"/tmp/rixa_tex/temp.log", "w") as f:
            err_msg = f.read()
        raise Exception(f"Error compiling latex. Tail of log: {err_msg[:1000]}")

@plugfunc()
def draw_plot_3D(function, xstart=-5, xend=5, ystart=-5,yend=5):
    """
    Draw a 3D plot of a function

    This returns nothing, it immediately displays the plot.

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
    api.display(html="<!--PLOT3D-->"+fig.to_html(include_plotlyjs=False, full_html=False))



@plugfunc()
def draw_plot(function, x_range_start=-10, x_range_end=10, x_label="x", y_label="y", plot_title=None):
    """
    Draw a plot of a function that depends on x

    This returns nothing, it immediately displays the plot.

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
    if "x" not in function:
        raise ValueError("Function must contain x as the main variable")
    x = sympy.symbols('x')
    y = sympy.sympify(function)
    x_vals = list(np.linspace(x_range_start, x_range_end, 200))

    func = lambdify(x, y)
    y_vals = [func(val) for val in x_vals]
    fig = px.line(x=x_vals, y=y_vals, title=plot_title, labels={x_label: x_label, y_label: y_label})
    api.display(html="<!--PLOT2D-->"+fig.to_html(include_plotlyjs=False, full_html=False))

    return "Plot successfully displayed to user"




# @plugfunc()
# def solve_equation(equation):
#     """
#     Solve an equation of the form f(x)=0
#
#     Example: solve_equation("x**2-4") to solve x^2=4
#     :param equation: Equation as a string
#     :return: Solution as a list
#     """
#     x = sympy.symbols('x')
#     eq = sympy.sympify(equation)
#     sol = sympy.solve(eq, x)
#     return sol


# @plugfunc()
# def differentiate(function):
#     """
#     Differentiate a function
#
#     Example: differentiate("x**2+3") to differentiate x^2+3
#     :param function: Function as a string
#     :return: Derivative as a latex string
#     """
#     x = sympy.symbols('x')
#     y = sympy.sympify(function)
#     dy_dx = sympy.diff(y, x)
#     return str(dy_dx)


# @plugfunc()
# def integrate(function):
#     """
#     Integrate a function
#
#     Example: integrate("x**2+3") to integrate x^2+3
#     :param function: Function as a string
#     :return: Integral as a latex string
#     """
#     x = sympy.symbols('x')
#     y = sympy.sympify(function)
#     integral = sympy.integrate(y, x)
#     return str(integral)


# @plugfunc()
# def simplify_expression(expression):
#     """
#     Simplify an expression
#
#     Example: simplify_expression("x**2+2*x+1") to simplify x^2+2x+1
#     :param expression: Expression as a string
#     :return: Simplified expression as a latex string
#     """
#     x = sympy.symbols('x')
#     expr = sympy.sympify(expression)
#     simplified = sympy.simplify(expr)
#     return str(simplified)


@plugfunc()
def evaluate(expression, return_float=False):
    """
    Evaluate an expression

    Use this for accurate numerical evaluation of expressions. Simplification will be applied automatically.
    You can use float() to convert the result to a float.

    Example: evaluate("2^4*x+3*x") returns 19x
    evaluate("sin^2(x)+cos^2(x)") returns 1
    evaluate("sin(45^4)", return_float=True) returns -0.9973979699962756


    :param expression:
    :param return_float: If True, returns a float. Otherwise, returns a string. Will raise TypeError if expression contains symbols
    :return: Expression or number
    """
    if return_float:
        return float(sympy.simplify(expression))
    return str(sympy.simplify(expression))
    # return str(sympy.sympify(expression))

@plugfunc()
def display(url, is_image=False):
    """
    Display an URl or image

    Uses the built in dashboard functionality to display the URL in an iframe or image.
    This will display the object as a separate chat message, that the user can e.g. maximize, compare etc.

    Use this e.g. when a user requests to see a plot from the wolfram API, to ensure a consistent experience with draw_plot.

    Example: display("https://www.google.com")
    :param url: URL as a string
    :return:
    """
    if is_image:
        api.display(html=f'<img src="{url}" style="width:100%; height:100%;"/>')
    else:
        api.display(html=f'<iframe src="{url}" style="width:100%; height:100%;"></iframe>')


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
