"""This is an exemplary plugin for data exploration via pandas"""
from typing import Tuple
import pandas as pd
import numpy as np
from rixaplugin import global_init, worker_init, plugfunc, PluginVariable, api
import plotly.graph_objs as go
import plotly.express as px

# Plugin variables are a special type that will be filled by the plugin system
# These can be changed e.g. via config files, the remote, on a per user basis or other means
# Usually plugin variables are something that is meant to be flexible or require special handling
# If no default is specified and the variables is not set e.g. in a config file, the plugin system will raise an error
# before the plugin is loaded
# Non basic types like a pandas dataframe will be rejected if there is no serializer registered for them
file_name_var = PluginVariable("file_name", "data.csv", str)

base_df = None


# A function marked with this will be called before anything else, including workers.
# Actions taken here are therefore not thread or process dependent
# A global init function is not required
# A global init always takes the global context as an argument. Variables defined here are everywhere available
# in the plugin. Obviously you do not put non-threadsafe things here.
@global_init()
def init(global_ctx):
    global base_df
    file_name = file_name_var.get()
    try:
        base_df = pd.read_csv(file_name)
    except FileNotFoundError:
        # If a global_init function raises an exception, plugin loading will be aborted
        api.log_exception(f"File {file_name} not found")
        # The API always works.
        raise FileNotFoundError(f"File {file_name} not found")

@worker_init()
def worker_init(worker_ctx):
    # Called once before a worker is initialized.
    # This is the place to put call specific things

    # Here is no need as we only read from the dataframe
    pass

@plugfunc()
def mean(query: str = None):
    """
    Return mean of all columns or a specific part via query
    :param query: a pandas query string
    :return:
    """
    if query:
        return base_df.query(query).mean()
    return base_df.mean()

@plugfunc()
def minmax(column: str, query: str = None) -> Tuple[float, float]:
    """
    Return min and max of a column
    :param column: Name of the column
    :param query: a pandas query string
    :return: Tuple of min and max
    """
    if query:
        data = base_df.query(query)[column]
    else:
        data = base_df[column]
    return data.min(), data.max()

@plugfunc()
def hist(column: str, bins: int = 10, query: str = None) -> Tuple[go.Figure, list, list]:
    """
    Compute histogram of a column
    :param column: Name of the column
    :param bins:
    :param query: a pandas query string
    :return: Tuple of plotly figure, bins and counts
    """
    if query:
        data = base_df.query(query)[column]
    else:
        data = base_df[column]
    counts, bins = np.histogram(data, bins=bins)
    bins = 0.5 * (bins[:-1] + bins[1:])
    fig = px.bar(x=bins, y=counts, labels={'x': column, 'y': 'count'})
    return fig, bins, counts


@plugfunc()
def scatter_plot(x: str, y: str, query: str = None, color: str = None) -> go.Figure:
    """
    Generate a scatter plot between two columns
    :param x: Name of the column for x-axis
    :param y: Name of the column for y-axis
    :param query: a pandas query string
    :param color: Column name to color code data points
    :return: Plotly figure of the scatter plot
    """
    if query:
        data = base_df.query(query)
    else:
        data = base_df
    fig = px.scatter(data, x=x, y=y, color=color)
    return fig


@plugfunc()
def unique_values(column: str, query: str = None) -> pd.Series:
    """
    Return unique values in a column
    :param column: Name of the column
    :param query: a pandas query string
    :return: Series with unique values
    """
    if query:
        data = base_df.query(query)[column]
    else:
        data = base_df[column]
    return data.unique()


@plugfunc()
def summary_statistics(query: str = None) -> pd.DataFrame:
    """
    Return summary statistics (count, mean, std, min, 25%, 50%, 75%, max) for all columns or filtered by a query
    :param query: a pandas query string
    :return: DataFrame with summary statistics
    """
    if query:
        data = base_df.query(query)
    else:
        data = base_df
    return data.describe()



@plugfunc()
def correlation_matrix(query: str = None) -> go.Figure:
    """
    Compute and visualize correlation matrix of the DataFrame columns
    :param query: a pandas query string to filter data
    :return: Plotly figure of the heatmap of the correlation matrix
    """
    if query:
        data = base_df.query(query)
    else:
        data = base_df
    corr = data.corr()
    fig = px.imshow(corr, text_auto=True, aspect="auto", labels=dict(x="Column", y="Column", color="Correlation"))
    fig.update_xaxes(side="top")
    return fig