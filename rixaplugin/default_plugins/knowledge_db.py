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
from rixaplugin.internal import api as internal_api

from rixaplugin import _memory
import rixarag.database as database

#settings.DEFAULT_MAX_WORKERS = 1
settings.ACCEPT_REMOTE_PLUGINS = 0


@worker_init()
def worker_init():
    import multiprocessing
    rixaplugin.worker_context.proc_id = -1
    if gpu_distribution.get() is not None:
        import multiprocessing
        try:
            proc_id = int(multiprocessing.current_process().name.replace("ForkProcess-", ""))
        except:
            proc_id = 1
        rixaplugin.worker_context.proc_id = proc_id
        gpus = gpu_distribution.get().split(";")
        os.environ["CUDA_VISIBLE_DEVICES"] = gpus[proc_id - 1]
    database.load_model()



# @plugfunc()
# def query_db_as_string(query, top_k=3, min_score=0.5, query_tags=None,  max_chars=3500):
#     results = database.query(query, n_results=top_k)
#
#     result = ""
#     for i, row in df.iterrows():
#         result += f"TITLE: {row['document_title']}\nSUBTITLE: {row['subtitle'] if  'subtitle' in row else ''}\nID: {i}\n" \
#                   f"CONTENT: {row['content']}\n\n"
#     return result

@plugfunc()
def get_random_entries(collection="default", n_results=5):
    results = database.get_random_elements_inverted(n_results, collection)
    return results

@plugfunc()
def query_rag_db(queries, n_results=6):
    """
    Query the RAG database with multiple queries and return a formatted string with the results.

    If there is any chance that the user's question may be answered by any of the documents in the RAG database, use this function!
    Use the results to properly cite the source of the information.
    Do not answer questions about particle physics, astrophysics, theoretical physics etc. without consulting the RAG database first.
    If nothing is returned that is related to the question, you can answer the question yourself.
    However make clear that your answer is not based on specific documents and may not be accurate.

    Always query the RAG database, before writing any text!

    Use the provided document ID and double curly brackets to cite e.g. {{6641}}.
    The citations will be replaced with links to the respective documents and various information about the document.

    Only use multiple queries for distinct topics. Don't do e.g.
    query_rag_db(["CKM matrix", "Cabibbo-Kobayashi-Maskawa matrix"])
    Both queries will return the same results.
    The RAG system is good at looking for content and is not sensitive to the exact wording of the query.
    If you want more info on a topic, increase the number of results. This will result in much better coverage than rephrasing the query.

    The following documents are currently available:
    * The __entire__ Particle Data Group Review of Particle Physics (2023)
    * Stefan Weinzierl - Symmetries in physics
    * Stefan Weinzierl - Introduction to Monte Carlo methods
    * Oliver F. Piattella - Lecture Notes in Cosmology
    * I. Tkachev - ASTROPARTICLE PHYSICS
    * Wayne Hu - Lecture Notes on CMB Theory: From Nucleosynthesis to Recombination
    * Lars Bergstrom - Multi-messenger Astronomy and Dark Matter
    * M. Kachelriess - Lecture Notes on High Energy Cosmic Rays
    * Sean M. Carroll - Lecture Notes on General Relativity
    * Yuval Grossman, Philip Tanedo - Just a Taste - Lectures on Flavor Physics
    * N. Tuning - Lectures Notes on CP violation
    * Jeffrey D. Richman - HEAVYQUARK PHYSICS AND CP VIOLATION
    * Several thousand physics related Wikipedia articles

    :param queries: List of queries to be executed.
    :param n_results: Number of results per query.

    :return: Formatted string with the results.

    :Example:
    User asks: How does Kaon mixing work?
    Here we use two queries since the CKM matrix is important in the context of Kaon mixing. We also increase the number of results since
    it is a complex topic.
    >>> query_rag_db(["Kaon mixing", "CKM Matrix", ], n_results=7)
    User asks: Whats the vacuum expectation value?
    The database can directly take the question as a query. As it is simple we only use one query and reduce the number of results.
    >>> query_rag_db(["Whats the vacuum expectation value?"], n_results=3)
    """
    max_distance = 0.45
    max_chars = 5000
    collection = "physics"
    results = []
    n_results_per_query = [n_results // len(queries)] * len(queries)
    n_results_per_query[0] += n_results % len(queries)
    for i,query in enumerate(queries):
        result = results = database.query_inverted(query, n_results=n_results_per_query[i], collection=collection,
                                      max_distance=max_distance, maximum_chars=max_chars)
        results.extend(result)
        # print(result)
    context_str = ""
    used_ids = set()
    used_results = []
    for i in results:
        if i['id'] not in used_ids:
            used_ids.add(i['id'])
            context_str += f"\n****\nID: {i['id']}\n"
            context_str += f"DOCUMENT TITLE: {i['document_title']}\n" if "document_title" in i else ""
            context_str += f"TITLE: {i['title']}\n" if "title" in i else ""
            context_str += f"CONTENT: {i['content']}"
            used_results.append(i)
    user_api = internal_api.get_api()
    user_api.plugin_variables["USED_RESULTS"] = used_results
    return context_str


@plugfunc()
def query_db(query, collection="default", n_results=5, max_distance=0.45, max_chars=5000):
    print("Querying db", query[:5], "....")
    results = database.query_inverted(query, n_results=n_results, collection=collection,
                                      max_distance=max_distance, maximum_chars=max_chars)
    # import random, time
    # time.sleep(random.randint(1, 3))
    return results
