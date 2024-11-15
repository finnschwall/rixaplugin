from rixaplugin.decorators import plugfunc
import json
from datetime import datetime
from rixaplugin.internal import api


@plugfunc(local_only=True)
async def modify_client_settings(update_dic):
    default_dic = {"role": "global_settings", "content": {"chat_disabled": False,
                                            "website_title": "TEST",
                                            "chat_title": "TEST",
                                            "always_maximize_chat": False,
                                            "server_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")}}
    default_dic["content"].update(update_dic)
    await api.get_api().display(custom_msg=json.dumps(default_dic, ensure_ascii=True))



@plugfunc(local_only=True)
async def send_message(msg, level="info"):
    await api.get_api().show_message(msg, theme=level)
