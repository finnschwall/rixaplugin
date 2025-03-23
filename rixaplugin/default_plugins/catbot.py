import asyncio
import base64
from rixaplugin.decorators import plugfunc
import rixaplugin.sync_api as api
import urllib.request
import time


@plugfunc()
def get_cat(query_str=""):
    """
    Get a random cat image

    Examples:
    get_cat() -> Get a random cat image
    get_cat("/gif") -> Get a random cat gif. Attention: Gif is not combinable with any other query i.e. no tags, no text, no font size, no font color!
    get_cat("/says/Hello?fontSize=50")	Will return a random cat saying Hello (everything under fontSize 50 is hard to read)
    get_cat("/says/Hello?fontColor=:color")	Will return a random cat saying Hello with the specified font color, e.g. /says/Hello?fontColor=red
    get_cat("/cat/says/:text?fontSize=:size&fontColor=:color") Will return a random cat saying :text with text's :fontSize and text's :fontColor
    get_cat("/:tag") Will return a random cat with a :tag, e.g. /black for a black cat or /angry for an angry cat

    :return: This function immediately displays the cat image (if query is valid)
    """
    url = f"https://cataas.com/cat{query_str}"
    with urllib.request.urlopen(url, timeout=2000) as response:
        img_base64 = base64.b64encode(response.read()).decode()
        api.display(html=f'<img src="data:image/png;base64,{img_base64}" style="background-color:white;height:100%; width:auto"/>')

