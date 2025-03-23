from rixaplugin.decorators import plugfunc
import rixaplugin.sync_api as api
from rixaplugin import variables as var


tavily_key = var.PluginVariable("tavily_key", str,default="")

@plugfunc()
def display_website(url):
    """
    Display a website to the user
    :param url: URL of the website
    :return: This function immediately displays the website
    """
    if not url.startswith("https"):
        url = "https://" + url
    api.display(html=f'<iframe src="{url}" style="width:100%;height:100%;border:0"></iframe>')


@plugfunc()
def get_html(url):
    """
    Get the html of a website
    :param url: URL of the website
    :return: The html of the website
    """
    import requests
    return requests.get(url).text

@plugfunc()
def tavily_search(query, search_depth="basic", max_results = 3,  include_raw_content=False):
    """
    Do a websearch using tavily
    :param query: The search string
    :param search_depth: The search depth (basic or advanced)
    :param max_results: The maximum number of results
    :param include_raw_content:  Include the cleaned and parsed HTML content of each search result.
    :return: The search results (Website titles, URLs, content, optionally raw content and similarity scores)
    """
    import requests
    include_answer = False
    #:param include_answer: Include a short LLM based answer to original query
    url = "https://api.tavily.com/search"
    headers = {
        'Content-Type': 'application/json'
    }
    data = {
        'api_key': tavily_key.get(),
        "query": query,
        "search_depth": search_depth,
        "max_results": max_results,
        "include_answer": include_answer,
        "include_raw_content": include_raw_content
    }
    response = requests.post(url, headers=headers, json=data)
    return response.json()
