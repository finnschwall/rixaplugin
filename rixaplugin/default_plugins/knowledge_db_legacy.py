import os.path
import pickle

from rixaplugin.decorators import plugfunc, worker_init
from rixaplugin import worker_context as ctx
import rixaplugin
from rixaplugin import settings
import pandas as pd
import torch
from transformers import AutoModel, AutoTokenizer
import logging
import numpy as np

knowledge_logger = logging.getLogger("rixa.knowledge_db")

model_name = rixaplugin.variables.PluginVariable("model_name", str, default="Snowflake/snowflake-arctic-embed-m-long")
embedding_df_loc = rixaplugin.variables.PluginVariable("embedding_df_loc", str, default="")

chat_store_loc = rixaplugin.variables.PluginVariable("chat_store_loc", str, default=None)

settings.DEFAULT_MAX_WORKERS = 1
settings.ACCEPT_REMOTE_PLUGINS = 0


@worker_init()
def worker_init():
    ctx.embeddings_db = pd.read_pickle(embedding_df_loc.get() + "embeddings_df.pkl")
    ctx.doc_metadata_db = pd.read_pickle(embedding_df_loc.get() + "doc_metadata_df.pkl")
    with open(embedding_df_loc.get() + "embeddings.pkl", "rb") as f:
        ctx.embeddings_list = pickle.load(f)
    knowledge_logger.info(f"Loaded {len(ctx.embeddings_db)} entries from {embedding_df_loc.get()}")
    # model = AutoModel.from_pretrained("Snowflake/snowflake-arctic-embed-m-long", trust_remote_code=True, add_pooling_layer=False, safe_serialization=True)
    ctx.tokenizer = AutoTokenizer.from_pretrained(model_name.get())
    ctx.model = AutoModel.from_pretrained(model_name.get(), trust_remote_code=True,
                                          add_pooling_layer=False, safe_serialization=True)
    ctx.device = "cpu"
    if torch.cuda.is_available():
        ctx.device = "cuda"
    ctx.model.to(ctx.device)
    ctx.model.eval()


def _query_db(query, top_k=5, min_score=0.5, query_tags=None, max_chars=4000, username=None):
    df = ctx.embeddings_db
    query_prefix = 'Represent this sentence for searching relevant passages: '
    queries = [query]
    queries_with_prefix = [f"{query_prefix}{i}" for i in queries]
    query_tokens = ctx.tokenizer(queries_with_prefix, padding=True, truncation=True, return_tensors='pt', max_length=512)
    query_tokens.to(ctx.device)
    with torch.no_grad():
        query_embeddings = ctx.model(**query_tokens)[0][:, 0]
    query_embeddings = query_embeddings.cpu()
    query_embeddings = torch.nn.functional.normalize(query_embeddings, p=2, dim=1).numpy()

    if query_tags:
        filtered_df = df[df['tags'].apply(lambda tags: query_tags.issubset(tags))]
    else:
        filtered_df = df
    idx = list(filtered_df.index)
    filtered_embeddings = ctx.embeddings_list[idx]
    scores = np.dot(query_embeddings, filtered_embeddings.T).flatten()

    idx = np.argsort(scores)[-top_k:][::-1]
    ret_idx = np.where(scores[idx] > min_score)

    final_docs = filtered_df.iloc[idx].iloc[ret_idx]

    if username and chat_store_loc.get():
        with open(os.path.join(chat_store_loc.get(), f"{username}.txt"), "a") as f:
            f.write(f"QUERY: {query}\n")
            f.write(f"TOP SCORES: {sorted(scores)[:-5:-1]}\n")
            f.write(f"TOP DOCS: {final_docs}\n")
    final_scores = scores[idx][ret_idx]

    final_docs = final_docs.reset_index().rename(columns={'index': 'index'})
    final_results = pd.merge(final_docs, ctx.doc_metadata_db.drop("tags", axis=1), on="doc_id")
    final_results.drop(["creation_time", "source_file"], inplace=True, axis=1)
    # return final_results, final_scores

    if max_chars == 0 or max_chars == -1 or max_chars is None:
        return final_results, final_scores
    else:
        char_count = [len(i) for i in final_results["content"]]
        cumsum = np.cumsum(char_count)
        idx = np.where(cumsum < max_chars)
        return final_results.iloc[idx], final_scores[idx]



@plugfunc()
def query_db_as_string(query, top_k=3, min_score=0.5, query_tags=None,  max_chars=3500):
    df, scores = _query_db(query, top_k, min_score, query_tags, max_chars)
    result = ""
    for i, row in df.iterrows():
        result += f"TITLE: {row['document_title']}\nSUBTITLE: {row['subtitle'] if  'subtitle' in row else ''}\nID: {i}\n" \
                  f"CONTENT: {row['content']}\n\n"
    return result


@plugfunc()
def query_db(query, top_k=5, min_score=0.5, query_tags=None, max_chars=4000, username=None):
    filtered_df, scores = _query_db(query, top_k, min_score,  query_tags,max_chars, username)
    ret_df = filtered_df
    # for i in ret_df.columns:
    #     print(ret_df[i].value_counts())
    ret_df = ret_df.fillna('')
    ret_df['tags'] = ret_df['tags'].apply(list)
    ret_df = ret_df.to_dict(orient='records')

    return ret_df, scores
