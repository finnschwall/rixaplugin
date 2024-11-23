import os.path
import pickle

from rixaplugin.decorators import plugfunc, worker_init
from rixaplugin import worker_context as ctx
from rixaplugin import settings
import logging
import numpy as np
import rixaplugin
knowledge_logger = logging.getLogger("rixa.knowledge_db")

gpu_distribution = rixaplugin.variables.PluginVariable("GPU_DISTRIBUTION", str, default=None)


import rixarag.database as database

settings.DEFAULT_MAX_WORKERS = 1
settings.ACCEPT_REMOTE_PLUGINS = 0


@worker_init()
def worker_init():
    if gpu_distribution.get() is not None:
        import multiprocessing
        try:
            proc_id = int(multiprocessing.current_process().name.replace("ForkProcess-", ""))
        except:
            proc_id = 1
        gpus = gpu_distribution.get().split(";")
        os.environ["CUDA_VISIBLE_DEVICES"] = gpus[proc_id - 1]
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
def query_db(query, collection="default", n_results=5, max_distance=0.45, max_chars=5000):
    results = database.query_inverted(query, n_results=n_results, collection=collection,
                                      max_distance=max_distance, maximum_chars=max_chars)
    return results
