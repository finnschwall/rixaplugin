import logging

import click
import numpy as np
from numpy import float32
from sentence_transformers import SentenceTransformer, util
from sentence_transformers.util import cos_sim
from bs4 import BeautifulSoup
import re
import rixaplugin
import requests
import pandas as pd
import os
import regex as re
import xml.etree.ElementTree as ET

knowledge_logger = logging.getLogger("knowledge_db")

# sentence transformers code is commented out. Works great for small datasets but not for large ones
# There seems to be a memory problem when computing embeddings on GPU
# multilingual distiluse-base-multilingual-cased-v1
# all-mpnet-base-v2
# model = SentenceTransformer("msmarco-distilbert-base-v4")
# model = SentenceTransformer("Snowflake/snowflake-arctic-embed-m-long", trust_remote_code=True)


# Currently using https://huggingface.co/Snowflake/snowflake-arctic-embed-m-long (547 MiB)
# This looks very good https://huggingface.co/BAAI/bge-m3 but has 2.3 GB so not very economical. However explicitly mentions asymmetric similarity
#  also good but just english (1.7 gb) https://huggingface.co/Alibaba-NLP/gte-large-en-v1.5/tree/main
import torch
from transformers import AutoModel, AutoTokenizer

tokenizer = AutoTokenizer.from_pretrained('Snowflake/snowflake-arctic-embed-m-long')
model = AutoModel.from_pretrained('Snowflake/snowflake-arctic-embed-m-long', trust_remote_code=True,
                                  add_pooling_layer=False, safe_serialization=True)
device = "cpu"
if torch.cuda.is_available():
    device = "cuda"
model.to(device)
# tokenizer.to(device)
model.eval()

embedding_df_loc = rixaplugin.variables.PluginVariable("embedding_df_loc", str, default="embeddings.pkl")

if os.path.exists(embedding_df_loc.get()):
    embeddings_db = pd.read_pickle(embedding_df_loc.get())
else:
    embeddings_db = pd.DataFrame(columns=["document_title", "source", "content", "subtitle", "embedding"])
    embeddings_db.to_pickle(embedding_df_loc.get())


def reset_db():
    global embeddings_db
    embeddings_db = pd.DataFrame(columns=["document_title", "source", "content", "subtitle", "embedding"])
    embeddings_db.to_pickle(embedding_df_loc.get())


def html_to_entities(html_content, source="NOT SPECIFIED"):
    soup = BeautifulSoup(html_content, 'html.parser')
    page_title = soup.title.string

    content_dict = {}
    elements = soup.find_all(re.compile(r'h[1-6]|p'))
    current_heading = ""
    for element in elements:
        if element.name.startswith('h'):
            current_heading = element.get_text().strip()
            content_dict[current_heading] = ""
        elif element.name == 'p' and current_heading:
            content_dict[current_heading] += element.get_text().strip() + " "
    for heading, text in content_dict.items():
        content_dict[heading] = ' '.join(text.split())
    embeddings = []
    for name, item in content_dict.items():
        if not item or item == "":
            continue
        entry = {"document_title": page_title, "subtitle": name, "content": item,
                 "source": source}
        embeddings.append(entry)
    return embeddings


def urls_to_entities(links):
    entities = []
    for url in links:
        response = requests.get(url)
        if response.status_code == 200:
            entities += html_to_entities(response.text, url)
    return entities


def get_entities_from_wiki_xml(path):
    tree = ET.parse(path)
    root = tree.getroot()
    entities = []
    for page in root[1:]:
        text = page.find("{http://www.mediawiki.org/xml/export-0.10/}revision").find(
            "{http://www.mediawiki.org/xml/export-0.10/}text").text
        title = page.find("{http://www.mediawiki.org/xml/export-0.10/}title").text
        id = page.find("{http://www.mediawiki.org/xml/export-0.10/}id").text
        if "Category:" in title:
            continue

        def repl(matchobj):
            hit = matchobj.groups()[0]
            full = matchobj.group()
            if "|" not in full or "efn|" in full:
                return ""
            elif "math| " in full:
                return f"${re.sub(r'{{((?:[^{}]|(?R))*)}}', repl, hit[6:])}$"
            elif "|" in hit:
                hit = re.sub(r"\|link=y", r"", full)
                if "10^|" in hit:
                    return f"10^{hit[6:-2]}"
                hit = re.sub(r"{{(.*?)\|(.*?)}}", r"\2", hit)
                return hit
            else:
                return full

        sections = re.split(r'={2,5}\s*(.*?)\s*={2,5}', text)
        headers = [title] + sections[1::2]
        section_text = sections[0::2]
        sections = {i: j for i, j in zip(headers, section_text)}
        entries_to_remove = (
            'See also', 'Footnotes', "References", "Sources", "History", "External links", "Bibliography")
        for k in entries_to_remove:
            sections.pop(k, None)

        for i in sections:
            text = sections[i]
            text = text.replace("&lt;", "<")
            text = text.replace("&gt;", ">")
            text = re.sub(r'\[\[(.*?)(?:\|.*?)?\]\]', r'\1', text)
            text = re.sub(r"<ref (.*?)>(.*?)</ref>", '', text)
            text = re.sub(r"<ref>(.*?)</ref>", '', text)
            text = re.sub(r"<ref (.*?)>", '', text)
            text = re.sub(r"<math(.*?)>(.*?)</math>", r'$\2$', text)
            text = re.sub(r"<sub>(.*?)</sub>", r'$\1$', text)
            text = re.sub(r"<sup>(.*?)</sup>", r'^{\1}', text)
            text = re.sub("&nbsp;", " ", text)
            text = re.sub("\t;", "", text)
            text = re.sub(r" {2,20}", "", text)
            text = re.sub(r'{{((?:[^{}]|(?R))*)}}', repl, text)
            text = re.sub("\n", "", text)  # <ref></ref>
            text = re.sub(r"<ref>(.*?)</ref>", '', text)
            text = re.sub(r"\'\'\'(.*?)\'\'\'", r"'\1'", text)
            text = re.sub(r"\'\'(.*?)\'\'", r"'\1'", text)
            entity = {"document_title": title, "content": i + ":\n" + text,
                      "source": f"https://en.wikipedia.org/?curid={id}#" + "_".join(i.split(" ")),
                      "subtitle": i}
            entities.append(entity)
            # sections[i] = text
    return entities


def entity_list_to_df(entities):
    df = pd.DataFrame(entities)
    return df


from tqdm import tqdm


def calculate_embeddings(df):
    content_col = df["content"].tolist()
    total_rows = len(content_col)
    df["embedding"] = None
    # 8245MiB usage for model size 547 MiB with chunk size 100
    chunk_size = 100
    for start_idx in tqdm(range(0, total_rows, chunk_size)):
        end_idx = min(start_idx + chunk_size, total_rows)
        chunk = content_col[start_idx:end_idx]
        document_tokens = tokenizer(chunk, padding=True, truncation=True, return_tensors='pt',
                                    max_length=512)
        document_tokens.to(device)
        with torch.no_grad():
            doument_embeddings = model(**document_tokens)[0][:, 0]
        embeddings = torch.nn.functional.normalize(doument_embeddings, p=2, dim=1).to("cpu")
        for i, embedding in enumerate(embeddings, start=start_idx):
            df.at[i, "embedding"] = embedding
    return df
    # sentence transformers. chunking doesnt work. Probably tensors dont get sent back to cpu
    # content_col = df["content"].tolist()
    # total_rows = len(content_col)
    # chunk_size = 100
    # df["embedding"] = None
    # for start_idx in tqdm(range(0, total_rows, chunk_size)):
    #     end_idx = min(start_idx + chunk_size, total_rows)
    #     chunk = content_col[start_idx:end_idx]
    #     embeddings = model.encode(chunk, convert_to_tensor=False, show_progress_bar=False)
    #     # print(embeddings)
    #     for i, embedding in enumerate(embeddings):
    #         # print(embedding)
    #         df.at[i + start_idx, "embedding"] = embedding
    # return df


def add_wiki(path_to_xml, tags):
    global embeddings_db
    entities = get_entities_from_wiki_xml(path_to_xml)
    df = entity_list_to_df(entities)
    knowledge_logger.info(f"Parsed {len(df)} entities from {path_to_xml}\n"
                          f"Starting to calculate embeddings. This may take a while.")
    df = calculate_embeddings(df)
    df['tags'] = [tags for _ in range(len(df))]
    embeddings_db = pd.concat([embeddings_db, df], ignore_index=True)
    embeddings_db.to_pickle(embedding_df_loc.get())


def add_urls(urls, tags):
    global embeddings_db
    entities = urls_to_entities(urls)
    df = entity_list_to_df(entities)
    df = calculate_embeddings(df)
    df['tags'] = [tags for _ in range(len(df))]
    embeddings_db = pd.concat([embeddings_db, df], ignore_index=True)
    embeddings_db.to_pickle(embedding_df_loc.get())


def query_db_as_string(query, top_k=3, query_tags=None, embd_db=None):
    df, scores = query_db(query, top_k, query_tags, embd_db)
    result = ""
    for i, row in df.iterrows():
        result += f"DOCUMENT TITLE: {row['document_title']}\nDOCUMENT SOURCE: {row['source']}\nSUBTITLE: {row['content']}\n\n"
    return result


def query_db(query, top_k=5, query_tags=None, embd_db=None):
    global embeddings_db
    if not embd_db:
        embd_db = embeddings_db
    query_prefix = 'Represent this sentence for searching relevant passages: '
    queries = [query]
    queries_with_prefix = ["{}{}".format(query_prefix, i) for i in queries]
    query_tokens = tokenizer(queries_with_prefix, padding=True, truncation=True, return_tensors='pt', max_length=512)
    query_tokens.to(device)
    with torch.no_grad():
        query_embeddings = model(**query_tokens)[0][:, 0]
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
    idx = reversed(np.argsort(scores[0]))[:5]
    scores = scores[0][idx].tolist()
    return filtered_df.iloc[idx], scores

    # for sentence transformers library
    # if not embd_db:
    #     embd_db = embeddings_db
    # query_embedding = model.encode(query, convert_to_tensor=False)
    # if query_tags:
    #     filtered_df = embd_db[embd_db['tags'].apply(lambda tags: query_tags.issubset(tags))]
    # else:
    #     filtered_df = embd_db
    # embd_series = filtered_df["embedding"]
    # arr = np.ndarray((len(embd_series), len(embd_series[0])), dtype=float32)
    # for i, x in enumerate(embd_series):
    #     arr[i] = x
    # scores = util.semantic_search(query_embedding, arr.astype(float32), top_k=top_k)
    # ids = [i["corpus_id"] for i in scores[0]]
    # scores = [i["score"] for i in scores[0]]
    # return filtered_df.iloc[ids], scores
