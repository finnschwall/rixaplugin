from rixaplugin.decorators import plugfunc
# from rixaplugin.api import PublicSyncApi as api
import rixaplugin.sync_api as api
import time


# import sync_api

@plugfunc()
def test_html_display():
    html_render_example = """<h1>Test</h1>
    <p>Test paragraph</p>
    <div style="color: red;">Red text</div>"""
    api.display(html=html_render_example)


@plugfunc()
def test_plotly():
    try:
        import plotly.express as px
        import pandas as pd
    except ImportError:
        print("Plotly and/or pandas not installed")
        return
    df = pd.DataFrame({
        "x": [1, 2, 3, 4],
        "y": [10, 11, 12, 13]
    })
    fig = px.line(df, x="x", y="y")
    api.display(plotly=fig)


@plugfunc()
def test_log():
    api.log.info("This is an info message")
    api.log.warning("This is a warning message")
    api.log.error("This is an error message")
    api.log.critical("This is a critical message")
    try:
        raise ValueError("This is a test exception")
    except ValueError as e:
        api.log.exception("This is an exception message")


@plugfunc()
def test_signature_and_doc_compile(var1, another_var: str, var3=5, var4: int = 6):
    """
    This is a test function to check if the signature and docstring are compiled correctly
    :param var1: This is a test parameter
    :param another_var: This is another test parameter
    :param var3: This is a test parameter with a default value
    :param var4: This is another test parameter with a default value
    """
    print("This is a test function")


@plugfunc()
def test_return_single_value():
    return 5


@plugfunc()
def test_return_multiple_values():
    time.sleep(1)
    return 5, 6


@plugfunc()
def test_var_args_and_kwargs(*args, **kwargs):
    print("args:", args)
    print("kwargs:", kwargs)


@plugfunc()
def test_exception():
    raise ValueError("This is a test exception")


@plugfunc()
def test_print(var1):
    print("I am test_print:", var1)


@plugfunc()
def test(var1):
    pass
