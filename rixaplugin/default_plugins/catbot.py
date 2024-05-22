import base64
from rixaplugin.decorators import plugfunc
import rixaplugin.sync_api as api
import urllib.request

@plugfunc()
def get_cat(query_str=""):
    """
    Get a random cat image

    Examples:
    get_cat() -> Get a random cat image
    get_cat("/gif") -> Get a random cat gif
    get_cat("/says/Hello?fontSize=50")	Will return a random cat saying Hello (everything under fontSize 50 is hard to read)
    get_cat("/cat/black")	Will return a random black cat. Black can be replaced by any tag. This does not work for /gif

    :return: This function immediately displays the cat image (if query is valid)
    """
    url = f"https://cataas.com/cat{query_str}"

    with urllib.request.urlopen(url) as response:
        img_base64 = base64.b64encode(response.read()).decode()
        api.display(html=f'<img src="data:image/png;base64,{img_base64}" style="background-color:white;height:100%; width:auto"/>')

