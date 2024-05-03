from rixaplugin.decorators import plugfunc, worker_init
from rixaplugin import worker_context as ctx
import rixaplugin
from rixaplugin import settings
import pandas as pd
import torch
from transformers import AutoModel, AutoTokenizer
import logging
import numpy as np

knowledge_logger = logging.getLogger("knowledge_db")

model_name = rixaplugin.variables.PluginVariable("model_name", str, default="Snowflake/snowflake-arctic-embed-m-long")
embedding_df_loc = rixaplugin.variables.PluginVariable("embedding_df_loc", str, default="embeddings.pkl")

settings.DEFAULT_MAX_WORKERS = 1
settings.ACCEPT_REMOTE_PLUGINS = 0

@worker_init()
def worker_init():
    ctx.tokenizer = AutoTokenizer.from_pretrained(model_name.get())
    ctx.model = AutoModel.from_pretrained(model_name.get(), trust_remote_code=True,
                                      add_pooling_layer=False, safe_serialization=True)
    ctx.device = "cpu"
    if torch.cuda.is_available():
        ctx.device = "cuda"
    ctx.model.to(ctx.device)
    ctx.model.eval()

    ctx.embeddings_db = pd.read_pickle(embedding_df_loc.get())
    knowledge_logger.info(f"Loaded {len(ctx.embeddings_db)} entries from {embedding_df_loc.get()}")


def _query_db(query, top_k=5, query_tags=None, min_score = 0.5, embd_db=None):
    if not embd_db:
        embd_db = ctx.embeddings_db
    query_prefix = 'Represent this sentence for searching relevant passages: '
    queries = [query]
    queries_with_prefix = ["{}{}".format(query_prefix, i) for i in queries]
    query_tokens = ctx.tokenizer(queries_with_prefix, padding=True, truncation=True, return_tensors='pt', max_length=512)
    query_tokens.to(ctx.device)
    with torch.no_grad():
        query_embeddings = ctx.model(**query_tokens)[0][:, 0]
    query_embeddings = query_embeddings.cpu()
    query_embeddings = torch.nn.functional.normalize(query_embeddings, p=2, dim=1)
    if query_tags:
        filtered_df = embd_db[embd_db['tags'].apply(lambda tags: query_tags.issubset(tags))]
    else:
        filtered_df = embd_db
    embd_series = filtered_df["embedding"]
    arr = torch.zeros(len(embd_series), len(embd_series[0]), dtype=torch.float32)
    for i, x in enumerate(embd_series):
        arr[i] = x
    scores = torch.mm(query_embeddings, arr.transpose(0, 1))

    values, indices = torch.sort(scores, descending=True)

    filtered_indices = indices[0][values[0] > min_score][:top_k]
    filtered_scores = values[0][values[0] > min_score][:top_k].tolist()
    filtered_rows = filtered_df.iloc[filtered_indices.cpu().numpy()]

    return filtered_rows, filtered_scores
    idx = reversed(np.argsort(scores[0]))[:top_k]
    scores = scores[0][idx].tolist()
    return filtered_df.iloc[idx], scores


@plugfunc()
def query_db_as_string(query, top_k=3, query_tags=None, min_score=0.5):
    df, scores = _query_db(query, top_k, query_tags, min_score)
    result = ""
    for i, row in df.iterrows():
        result += f"DOCUMENT TITLE: {row['document_title']}\nSUBTITLE: {row['content']}\nDOCUMENT SOURCE: {row['source']}\n\n"
    return result

@plugfunc()
def query_db(query, top_k=5, query_tags=None, embd_db=None, min_score=0.5):
    filtered_df, scores = _query_db(query, top_k, query_tags, min_score)
    ret_df = filtered_df.drop("embedding", axis=1).reset_index()
    ret_df['tags'] = ret_df['tags'].apply(list)
    return ret_df.to_dict(orient='records'), scores