import rixaplugin.sync_api as api
from rixaplugin.decorators import plugfunc, worker_init
from rixaplugin import worker_context as ctx
import rixaplugin


import pandas as pd
import numpy as np
from scipy import stats
import plotly.express as px
import plotly.graph_objects as go
import joblib


data_location = rixaplugin.variables.PluginVariable("data_location", str, default="")

df = None

@worker_init()
def worker_init():
    global df
    if data_location.get().endswith(".pkl") or data_location.get().endswith(".jl"):
        df = joblib.load(data_location.get())
    else:
        df = pd.read_csv(data_location.get())


def apply_query(df, query=None):
    if query:
        return df.query(query)
    return df

@plugfunc()
def iloc(row, query=None):
    """
    Get the data at a specific row index.

    This can be used as a datapoint picker
    :param row: Row index
    """
    temp_df = apply_query(df, query)
    return temp_df.iloc[row:row+1]

@plugfunc()
def basic_info(query=None):
    """
    Get basic information about the dataset.
    :param query: pandas query string to filter the dataset
    """
    temp_df = apply_query(df, query)
    info_string = f"Dataset shape: {temp_df.shape}\n"
    info_string += f"Columns: {', '.join(temp_df.columns.tolist())}\n"
    info_string += "Data types:\n"
    for col, dtype in temp_df.dtypes.items():
        info_string += f"  {col}: {dtype}\n"
    return info_string

@plugfunc()
def descriptive_stats(query=None):
    """
    Get descriptive statistics for the dataset using pandas describe method.
    :param query: pandas query string to filter the dataset
    :return: Descriptive statistics as a string
    """
    temp_df = apply_query(df, query)
    return temp_df.describe().to_string()

@plugfunc()
def missing_values_analysis(query=None):
    """
    Get missing values analysis for the dataset.

    :param query: pandas query string to filter the dataset
    :return: Missing values analysis as a string
    """
    temp_df = apply_query(df, query)
    missing = temp_df.isnull().sum()
    missing_percent = 100 * missing / len(temp_df)
    result = "Missing Values Analysis:\n"
    for col in temp_df.columns:
        result += f"{col}: {missing[col]} ({missing_percent[col]:.2f}%)\n"
    return result


@plugfunc()
def count_entries(query=None):
    """
    Get the number of entries in the dataset.

    :param query: pandas query string to filter the dataset
    :return: Number of entries as a string
    """
    temp_df = apply_query(df, query)
    return f"Number of entries: {len(temp_df)}"


@plugfunc()
def unique_values_count(query=None):
    """
    Get unique values count for each column in the dataset.

    :param query: pandas query string to filter the dataset
    :return: Unique values count as a string
    """
    temp_df = apply_query(df, query)
    result = "Unique Values Count:\n"
    for col in temp_df.columns:
        result += f"{col}: {temp_df[col].nunique()}\n"
    return result

@plugfunc()
def distribution_analysis(column, query=None):
    """
    Perform distribution analysis for a numerical column in the dataset.

    :param column: The column to analyze
    :param query: pandas query string to filter the dataset
    :return: Distribution analysis as a string
    """
    temp_df = apply_query(df, query)
    if temp_df[column].dtype in ['int64', 'float64']:
        skewness = temp_df[column].skew()
        kurtosis = temp_df[column].kurtosis()
        _, p_value = stats.normaltest(temp_df[column].dropna())
        return f"Distribution Analysis for {column}:\n" \
               f"Skewness: {skewness:.2f}\n" \
               f"Kurtosis: {kurtosis:.2f}\n" \
               f"Normality Test p-value: {p_value:.4f}"
    else:
        return "Distribution analysis is only applicable to numerical columns."

@plugfunc()
def correlation_analysis(query=None):
    """
    Perform correlation analysis for the dataset.

    Additionally, display a correlation matrix heatmap to the user
    :param query: pandas query string to filter the dataset
    :return: Correlation analysis as a string
    """
    temp_df = apply_query(df, query)
    corr_matrix = temp_df.corr()
    result = "Correlation Matrix:\n"
    result += corr_matrix.to_string()

    mask = np.zeros_like(corr_matrix, dtype=bool)
    mask[np.triu_indices_from(mask)] = True
    df_corr_viz = corr_matrix.mask(mask).dropna(how='all').dropna('columns', how='all')
    fig = px.imshow(df_corr_viz, text_auto=True)
    api.display(html=fig.to_html(include_plotlyjs=False, full_html=False))
    return result

@plugfunc()
def outlier_detection(column, method='iqr', query=None):
    """
    Perform outlier detection for a numerical column in the dataset.

    :param column: Column to perform outlier detection on
    :param method: Outlier detection method. Choose from 'iqr' or 'zscore'
    :param query: pandas query string to filter the dataset
    :return: Outlier detection results as a string
    """
    temp_df = apply_query(df, query)
    if temp_df[column].dtype not in ['int64', 'float64']:
        return "Outlier detection is only applicable to numerical columns."

    if method == 'iqr':
        Q1 = temp_df[column].quantile(0.25)
        Q3 = temp_df[column].quantile(0.75)
        IQR = Q3 - Q1
        lower_bound = Q1 - 1.5 * IQR
        upper_bound = Q3 + 1.5 * IQR
        outliers = temp_df[(temp_df[column] < lower_bound) | (temp_df[column] > upper_bound)][column]
    elif method == 'zscore':
        z_scores = np.abs(stats.zscore(temp_df[column]))
        outliers = temp_df[z_scores > 3][column]
    else:
        return "Invalid method. Choose 'iqr' or 'zscore'."

    return f"Outlier Detection for {column} using {method} method:\n" \
           f"Number of outliers: {len(outliers)}\n" \
           f"Outlier values: {', '.join(map(str, outliers.tolist()))}"


@plugfunc()
def column_value_frequencies(column, top_n=10, query=None):
    """
    Get the top N value frequencies for a column in the dataset.

    :param column: Column to analyze
    :param top_n: Number of top values to display
    :param query: pandas query string to filter the dataset
    :return: Value frequencies as a string
    """
    temp_df = apply_query(df, query)
    freq = temp_df[column].value_counts().nlargest(top_n)
    result = f"Top {top_n} value frequencies for {column}:\n"
    for value, count in freq.items():
        result += f"{value}: {count}\n"
    return result

@plugfunc()
def data_sampling(n=5,  query=None):
    """
    Sample the dataset. Additionally, display the sample(s) to the user.

    :param n: Number of samples to return
    :param random_state:
    :param query: pandas query string to filter the dataset
    :return: Sample(s)
    """
    temp_df = apply_query(df, query)
    sample = temp_df.sample(n=min(n, len(temp_df)))
    api.display(html=sample.to_html())
    return sample

@plugfunc()
def plot_histogram(column, nbins = 10, query=None):
    """
    Plot a histogram for a numerical column in the dataset.

    :param column: Column to plot histogram for
    :param nbins: Number of bins for the histogram
    :param query: pandas query string to filter the dataset
    :return: Histogram summarized
    """
    temp_df = apply_query(df, query)
    if temp_df[column].dtype not in ['int64', 'float64']:
        return "Histogram is only applicable to numerical columns."

    fig = px.histogram(temp_df, x=column, title=f'Histogram of {column}', nbins=nbins)
    api.display(html=fig.to_html(include_plotlyjs=False, full_html=False))

    # Return a summary for the LLM
    hist, bin_edges = np.histogram(temp_df[column].dropna(), bins=nbins)
    summary = f"Histogram summary for {column}:\n"
    for i in range(len(hist)):
        summary += f"Bin {i + 1}: {bin_edges[i]:.2f} to {bin_edges[i + 1]:.2f}, Count: {hist[i]}\n"
    return summary



@plugfunc()
def plot_boxplot(column, query=None):
    """
    Plot a box plot for a numerical column in the dataset.

    :param column: Column to plot box plot for
    :param query: pandas query string to filter the dataset
    :return: Box plot summarized
    """
    temp_df = apply_query(df, query)
    if temp_df[column].dtype not in ['int64', 'float64']:
        return "Box plot is only applicable to numerical columns."

    fig = px.box(temp_df, y=column, title=f'Box Plot of {column}')
    api.display(html=fig.to_html(include_plotlyjs=False, full_html=False))

    # Return a summary for the LLM
    summary_stats = temp_df[column].describe()
    return f"Box plot summary for {column}:\n" \
           f"Minimum: {summary_stats['min']:.2f}\n" \
           f"Q1: {summary_stats['25%']:.2f}\n" \
           f"Median: {summary_stats['50%']:.2f}\n" \
           f"Q3: {summary_stats['75%']:.2f}\n" \
           f"Maximum: {summary_stats['max']:.2f}"

@plugfunc()
def plot_scatter(x_column, y_column, query=None):
    """
    Plot a scatter plot for two numerical columns in the dataset.

    :param x_column: First column for x-axis
    :param y_column: Second column for y-axis
    :param query: pandas query string to filter the dataset
    :return: Scatter plot summarized
    """
    temp_df = apply_query(df, query)
    if temp_df[x_column].dtype not in ['int64', 'float64'] or temp_df[y_column].dtype not in ['int64', 'float64']:
        return "Scatter plot is only applicable to numerical columns."

    fig = px.scatter(temp_df, x=x_column, y=y_column, title=f'Scatter Plot: {x_column} vs {y_column}')
    api.display(html=fig.to_html(include_plotlyjs=False, full_html=False))

    # Return a summary for the LLM
    correlation = temp_df[[x_column, y_column]].corr().iloc[0, 1]
    return f"Scatter plot summary for {x_column} vs {y_column}:\n" \
           f"Correlation coefficient: {correlation:.2f}"


