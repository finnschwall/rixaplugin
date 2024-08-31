import base64
from io import BytesIO

from sklearn.neighbors import NearestNeighbors

import rixaplugin.sync_api as api
from rixaplugin.decorators import plugfunc, worker_init
from rixaplugin import worker_context as ctx
import rixaplugin

import joblib
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objs as go
from sklearn.inspection import PartialDependenceDisplay
from sklearn.tree import DecisionTreeClassifier, DecisionTreeRegressor, plot_tree
from sklearn.compose import ColumnTransformer
from sklearn.preprocessing import OneHotEncoder
import matplotlib.pyplot as plt
from sklearn.metrics import confusion_matrix, roc_curve, auc
import math
import dice_ml
from dice_ml.utils import helpers


full_data_location = rixaplugin.variables.PluginVariable("full_data_location", str, default="")
data_location = rixaplugin.variables.PluginVariable("data_location", str, default="")
y_location = rixaplugin.variables.PluginVariable("y_location", str, default="")
model_location = rixaplugin.variables.PluginVariable("model_location", str, default="")
to_drop = rixaplugin.variables.PluginVariable("to_drop", str, default="")
target_column = rixaplugin.variables.PluginVariable("target_column", str, default="adr")

model=None
df_full = None
feature_names = None
X = None
y = None

@worker_init()
def worker_init():
    global df_full, model, X, y, feature_names
    df_full = joblib.load(full_data_location.get())
    X = joblib.load(data_location.get())
    y = joblib.load(y_location.get())

    feature_names = list(X.columns)
    model = joblib.load(model_location.get())


def apply_query(query=None):
    if query:
        return X.query(query)
    return X


@plugfunc()
def get_currently_selected_datapoint():
    """
    Get the datapoint that is currently selected by the user
    """

    return X.iloc[0:1]


@plugfunc()
def feature_importance():
    """
    Calculate and plot feature importance for the model.
    """
    cur_model = model
    if hasattr(model, '_final_estimator'):
        cur_model = model._final_estimator

    if hasattr(cur_model, 'feature_importances_'):
        importances = cur_model.feature_importances_
    else:
        importances = np.abs(cur_model.coef_[0])

    fig = px.bar(x=feature_names, y=importances,
                 labels={'x': 'Features', 'y': 'Importance'},
                 title='Feature Importance')
    api.display(html=fig.to_html(include_plotlyjs=False, full_html=False))


@plugfunc()
def partial_dependence_plot(feature):
    """
    Generate a Partial Dependence Plot for a specific feature.

    :param feature: The name of the feature to plot
    """
    feature_index = feature_names.index(feature)
    pdp = PartialDependenceDisplay.from_estimator(model, X, [feature_index])
    fig = px.line(x=pdp.pd_results[0]['values'][0],
                  y=pdp.pd_results[0]['average'][0],
                  labels={'x': feature, 'y': 'Partial Dependence'},
                  title=f'Partial Dependence Plot for {feature}')
    api.display(html=fig.to_html(include_plotlyjs=False, full_html=False))


@plugfunc()
def feature_interaction_analysis(feature1, feature2, query = None):
    """
    Analyze and visualize the interaction between two features.

    Warning: This function will take a long time to run. Ask the user to confirm before running.
    :param feature1: First feature name
    :param feature2: Second feature name
    :param query: Query to filter the dataset from which the interaction is analyzed
    :return: The Partial Dependence Plot results
    """
    f1_index = feature_names.index(feature1)
    f2_index = feature_names.index(feature2)

    pdp = PartialDependenceDisplay.from_estimator(model, X, [(f1_index, f2_index)], grid_resolution=10, n_jobs=4)
    tmpfile = BytesIO()
    plt.savefig(tmpfile, format='png')
    encoded = base64.b64encode(tmpfile.getvalue()).decode('utf-8')
    html = 'Decision tree' + '<img src=\'data:image/png;base64,{}\'>'.format(encoded)
    api.display(html=html)
    return pdp.pd_results

@plugfunc()
def decision_tree_surrogate(decision_tree_depth=3, query=None):
    """
    Generate a decision tree surrogate for the model and display it.

    :param decision_tree_depth: Depth of the decision tree
    :param query: Query to filter the dataset that is used to generate the surrogate
    """
    if isinstance(model, DecisionTreeClassifier) or isinstance(model, DecisionTreeRegressor):
        return "The model is already a decision tree. No surrogate needed."

    categorical_features = [col for col in X.columns if X[col].dtype == 'object']

    preprocessor = ColumnTransformer(
        transformers=[
            ('cat', OneHotEncoder(), categorical_features)
        ],
        remainder='passthrough'
    )
    X_new = apply_query(query)
    X_transformed = preprocessor.fit_transform(X_new)
    surrogate = DecisionTreeClassifier(max_depth=decision_tree_depth)
    surrogate.fit(X_transformed, model.predict(X_new))
    plt.figure(figsize=(20, 10))
    plot_tree(surrogate, filled=True, feature_names=preprocessor.get_feature_names_out())
    tmpfile = BytesIO()
    plt.savefig(tmpfile, format='png')
    encoded = base64.b64encode(tmpfile.getvalue()).decode('utf-8')
    html = 'Decision tree' + '<img src=\'data:image/png;base64,{}\'>'.format(encoded)
    api.display(html=html)


@plugfunc()
def similar_instance_retrieval(datapoint, n_neighbors=5, query=None):
    """
    Retrieve similar instances to a specific data point inside the training data.
    Also displays the similar instances in a table to the user.

    :param datapoint: The data point for which to retrieve similar instances
    :param n_neighbors: Number of similar instances to retrieve
    :param query: Query to filter the dataset
    :return: The similar instances
    """
    X_new = apply_query(query)
    nn = NearestNeighbors(n_neighbors=n_neighbors + 1, metric='euclidean')

    categorical_features = [col for col in X_new.columns if X_new[col].dtype == 'object']

    preprocessor = ColumnTransformer(
        transformers=[
            ('cat', OneHotEncoder(), categorical_features)
        ],
        remainder='passthrough'
    )
    X_transformed = preprocessor.fit_transform(X_new)
    nn.fit(X_transformed)
    distances, indices = nn.kneighbors(preprocessor.transform(datapoint))
    similar_instances = X.iloc[indices[0][1:]]
    api.display(html=similar_instances.to_html(justify="left", border=1, classes="table"))
    return str(similar_instances)

@plugfunc()
def what_if_analysis(datapoint, feature, range_min, range_max, steps=10, query=None):
    """
    Perform a What-If analysis by varying a specific feature.

    :param datapoint: The base datapoint to modify
    :param feature: The feature to vary
    :param range_min: Minimum value for the feature
    :param range_max: Maximum value for the feature
    :param steps: Number of steps between min and max
    :param query: Query to filter the dataset
    :return: The predictions for the modified datapoints
    """
    values = np.linspace(range_min, range_max, steps)

    predictions = []

    for value in values:
        modified_datapoint = datapoint.copy()
        modified_datapoint[feature] = value
        predictions.append(model.predict_proba(modified_datapoint)[0][1])

    fig = px.line(x=values, y=predictions, labels={'x': feature, 'y': 'Prediction Probability'},
                  title=f'What-If Analysis for {feature}')

    api.display(html=fig.to_html(include_plotlyjs=False, full_html=False))
    return predictions


@plugfunc()
def roc_auc_plot():
    """
    Plot the ROC curve and calculate AUC for binary classification.

    :return: The AUC score
    """
    y_pred_proba = model.predict_proba(X)[:, 1]
    print(y)
    print(y_pred_proba)
    fpr, tpr, _ = roc_curve(y, y_pred_proba)
    roc_auc = auc(fpr, tpr)

    fig = px.line(x=fpr, y=tpr, labels={'x': 'False Positive Rate', 'y': 'True Positive Rate'},
                  title=f'ROC Curve (AUC = {roc_auc:.2f})')
    fig.add_shape(type='line', line=dict(dash='dash'), x0=0, x1=1, y0=0, y1=1)
    api.display(html=fig.to_html(include_plotlyjs=False, full_html=False))
    return roc_auc


def display_df(df, org):
    """copied with love from https://github.com/interpretml/DiCE/blob/main/dice_ml/diverse_counterfactuals.py#L132"""
    newdf = df.values.tolist()
    for ix in range(df.shape[0]):
        for jx in range(len(org)):
            if not isinstance(newdf[ix][jx], str):
                if math.isclose(newdf[ix][jx], org[jx], rel_tol=abs(org[jx]/10000)):
                    newdf[ix][jx] = '-'
                else:
                    newdf[ix][jx] = str(newdf[ix][jx])
            else:
                if newdf[ix][jx] == org[jx]:
                    newdf[ix][jx] = '-'
                else:
                    newdf[ix][jx] = str(newdf[ix][jx])
    df_new= pd.DataFrame(newdf, columns=df.columns, index=df.index)
    df_new = df_new.loc[:, (df_new != '-').any()]
    return df_new


@plugfunc()
def generate_counterfactuals(query_instance, n_cfs=5, query=None):
    """
    Generate counterfactuals for a datapoint. CFs are displayed in a table.

    This generates a sparse representation (columns that are not changed are not shown)
    :param query_instance: The data point for which to generate counterfactuals
    :param n_cfs: Number of counterfactuals to generate
    :param query: Query to filter the dataset
    :return:
    """
    if query:
        df_new = df_full.query(query)
    else:
        df_new = df_full
    dice_data = dice_ml.Data(dataframe=df_new, outcome_name=target_column.get(), continuous_features=[])
    dice_model = dice_ml.Model(model=model, backend='sklearn')
    exp = dice_ml.Dice(dice_data, dice_model)
    dice_exp = exp.generate_counterfactuals(query_instance, total_CFs=n_cfs, desired_class="opposite")

    cf_df = display_df(dice_exp.cf_examples_list[0].final_cfs_df, query_instance.iloc[0] if isinstance(query_instance, pd.DataFrame) else query_instance)
    cf_html = cf_df.to_html(justify="left", border=1, classes="table")
    cf_html = """""" +cf_html
    api.display(html=cf_html)
    return str(cf_df)
