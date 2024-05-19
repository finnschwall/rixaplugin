import datetime
import json
import logging
import pickle

import numpy as np
# from sentence_transformers import SentenceTransformer, util
# from sentence_transformers.util import cos_sim
from bs4 import BeautifulSoup
import re
import rixaplugin
import requests
import pandas as pd
import os
import regex as re
import xml.etree.ElementTree as ET
from tqdm import tqdm

import torch
from transformers import AutoModel, AutoTokenizer

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


model = None
tokenizer = None
device = None
embeddings_db = None
embeddings_list = None
doc_metadata_db=None
current_doc_id = 0

def init():
    global embeddings_db
    global model
    global tokenizer
    global device
    global embeddings_list, doc_metadata_db, current_doc_id

    tokenizer = AutoTokenizer.from_pretrained('Snowflake/snowflake-arctic-embed-m-long')
    model = AutoModel.from_pretrained('Snowflake/snowflake-arctic-embed-m-long', trust_remote_code=True,
                                      add_pooling_layer=False, safe_serialization=True)

    # tokenizer = AutoTokenizer.from_pretrained('sentence-transformers/msmarco-distilbert-base-v4')
    # model = AutoModel.from_pretrained('sentence-transformers/msmarco-distilbert-base-v4', trust_remote_code=True,)

    device = "cpu"
    if torch.cuda.is_available():
        device = "cuda"
    model.to(device)
    model.eval()

    if os.path.exists("embeddings_df.pkl"):
        embeddings_db = pd.read_pickle("embeddings_df.pkl")
        doc_metadata_db = pd.read_pickle("doc_metadata_df.pkl")
        with open("embeddings.pkl", "rb") as f:
            embeddings_list = pickle.load(f)
        current_doc_id = doc_metadata_db["doc_id"].max()
    else:
        reset_db()


def reset_db():
    global embeddings_db, embeddings_list, doc_metadata_db, current_doc_id
    current_doc_id = 0
    embeddings_db = pd.DataFrame(columns=["doc_id", "header", "subheader", "location", "url", "tags", "content", ])
    embeddings_list = None
    doc_metadata_db = pd.DataFrame(
        columns=["doc_id", "document_title", "source", "authors", "publisher", "tags", "creation_time", "source_file"])


def query_db_as_string(query, top_k=3, query_tags=None, embd_db=None):
    df, scores = query_db(query, top_k, query_tags, embd_db)
    result = ""
    for i, row in df.iterrows():
        result += f"DOCUMENT TITLE: {row['document_title']}\nDOCUMENT SOURCE: {row['source']}\nSUBTITLE: {row['content']}\n\n"
    return result


def query_db(query, top_k=5, min_score=0.5, query_tags=None, max_chars=3500):
    global embeddings_db, embeddings_list, doc_metadata_db
    df = embeddings_db
    query_prefix = 'Represent this sentence for searching relevant passages: '
    queries = [query]
    queries_with_prefix = [f"{query_prefix}{i}" for i in queries]
    query_tokens = tokenizer(queries_with_prefix, padding=True, truncation=True, return_tensors='pt', max_length=512)
    query_tokens.to(device)
    with torch.no_grad():
        query_embeddings = model(**query_tokens)[0][:, 0]
    query_embeddings = query_embeddings.cpu()
    query_embeddings = torch.nn.functional.normalize(query_embeddings, p=2, dim=1).numpy()

    if query_tags:
        filtered_df = df[df['tags'].apply(lambda tags: query_tags.issubset(tags))]
    else:
        filtered_df = df
    idx = list(filtered_df.index)
    filtered_embeddings = embeddings_list[idx]
    scores = np.dot(query_embeddings, filtered_embeddings.T).flatten()
    idx = np.argsort(scores)[-top_k:][::-1]
    ret_idx = np.where(scores[idx] > min_score)

    final_docs = filtered_df.iloc[idx].iloc[ret_idx]
    final_scores = scores[idx][ret_idx]

    final_results = pd.merge(final_docs, doc_metadata_db.drop("tags", axis=1), on="doc_id")
    final_results.drop(["creation_time", "source_file"], inplace=True, axis=1)

    if max_chars == 0 or max_chars == -1 or max_chars is None:
        return final_results, final_scores
    else:
        char_count = [len(i) for i in final_results["content"]]
        cumsum = np.cumsum(char_count)
        idx = np.where(cumsum < max_chars)
        return final_results.iloc[idx], final_scores[idx]


def from_json(path):
    global doc_metadata_db, embeddings_db, embeddings_list, current_doc_id
    with open(path, "r") as f:
        data = json.load(f)

    metadata = data[0]
    current_doc_id += 1
    doc_id = current_doc_id

    mod_time = os.path.getmtime(path)
    metadata_entry = {"doc_id": doc_id,
                      "document_title": metadata["title"] if "title" in metadata else metadata["document_title"],
                      "source": metadata["source"] if "source" in metadata else metadata["source_url"],
                      "tags": metadata["tags"],
                      "creation_time": datetime.datetime.utcfromtimestamp(mod_time).strftime('%H:%M %d/%m/%Y'),
                      "source_file": os.path.basename(path),
                      "authors": metadata.get("authors", None),
                      "publisher": metadata.get("publisher", None)}

    content_entries = []
    for entry in data[1:]:
        content_entries.append({"doc_id": doc_id, "content": entry["content"], "tags": metadata["tags"],
                                "header": entry["header"] if "header" in entry else None,
                                "subheader": entry["subheader"] if "subheader" in entry else "",
                                "location": f'Page {entry["page"]}' if "page" in entry else ""})

    add_entry(metadata_entry, content_entries)


def add_entry(metadata_entry, content_entries):
    global doc_metadata_db, embeddings_db, embeddings_list

    doc_metadata_db = pd.concat([doc_metadata_db, pd.DataFrame([metadata_entry])], ignore_index=True)
    doc_metadata_db = doc_metadata_db.convert_dtypes()
    df = pd.DataFrame(content_entries)
    additional_embeddings = calculate_embeddings(df)
    if embeddings_list is None:
        embeddings_list = additional_embeddings
    else:
        embeddings_list=np.concatenate((embeddings_list, additional_embeddings,), axis=0)
    # embeddings_list.append(additional_embeddings)
    with open("embeddings.pkl", "wb") as f:
        pickle.dump(embeddings_list, f)
    embeddings_db = pd.concat([embeddings_db, df], ignore_index=True).convert_dtypes()
    embeddings_db.to_pickle("embeddings_df.pkl")
    doc_metadata_db.to_pickle("doc_metadata_df.pkl")



def calculate_embeddings(df):
    global tokenizer, model, device
    content_col = df["content"].tolist()
    total_rows = len(content_col)
    # df["embedding"] = None
    # 8245MiB usage for model size 547 MiB with chunk size 100

    embeddings_list_temp = []
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
        for i in embeddings:
            embeddings_list_temp.append(i)
        # embeddings_list_temp.append(*embeddings)
        # print(embeddings.shape)
        # for i, embedding in enumerate(embeddings, start=start_idx):
        #     df.at[i, "embedding"] = embedding
    return np.array(embeddings_list_temp)


def add_wiki(path_to_xml, tags, name):
    global doc_metadata_db, current_doc_id
    current_doc_id += 1
    doc_id = current_doc_id
    entities = get_entities_from_wiki_xml(path_to_xml, tags, doc_id)

    doc_metadata = {"doc_id": doc_id, "authors":None, "publisher": "Wikipedia", "tags": tags, "source": "wikipedia.org",
"creation_time": datetime.datetime.now().strftime('%H:%M %d/%m/%Y'),
                    "source_file": os.path.basename(path_to_xml), "document_title": name}
    add_entry(doc_metadata, entities)


def add_urls(urls, tags):
    global embeddings_db
    entities = urls_to_entities(urls)
    df = entity_list_to_df(entities)
    df = calculate_embeddings(df)
    df['tags'] = [tags for _ in range(len(df))]
    embeddings_db = pd.concat([embeddings_db, df], ignore_index=True)
    embeddings_db.to_pickle(embedding_df_loc)



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


def get_entities_from_wiki_xml(path, tags, doc_id):
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
            entity = {"header": title, "content": i + ":\n" + text,
                      "url": f"https://en.wikipedia.org/?curid={id}#" + "_".join(i.split(" ")),
                      "subheader": i, "tags":tags, "doc_id": doc_id}
            entities.append(entity)
            # sections[i] = text
    return entities