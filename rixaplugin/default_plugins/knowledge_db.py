import os.path
import pickle

from rixaplugin.decorators import plugfunc, worker_init
from rixaplugin import worker_context as ctx
from rixaplugin import settings
import logging
import numpy as np

knowledge_logger = logging.getLogger("rixa.knowledge_db")
import rixarag.database as database

settings.DEFAULT_MAX_WORKERS = 1
settings.ACCEPT_REMOTE_PLUGINS = 0


@worker_init()
def worker_init():
    database.load_model()


@plugfunc()
def query_db_as_string(query, top_k=3, min_score=0.5, query_tags=None,  max_chars=3500):
    results = database.query(query, n_results=top_k)

    result = ""
    for i, row in df.iterrows():
        result += f"TITLE: {row['document_title']}\nSUBTITLE: {row['subtitle'] if  'subtitle' in row else ''}\nID: {i}\n" \
                  f"CONTENT: {row['content']}\n\n"
    return result


@plugfunc()
def query_db(query, collection="default", n_results=5, max_distance=0.7, max_chars=4000):
    results = database.query_inverted(query, n_results=n_results, collection=collection,
                                      max_distance=max_distance, maximum_chars=max_chars)
    return results
