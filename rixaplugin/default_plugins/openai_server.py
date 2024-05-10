import re

from rixaplugin import variables as var
from rixaplugin.decorators import global_init, worker_init, plugfunc
from rixaplugin import worker_context, execute

from rixaplugin.internal.memory import _memory

import rixaplugin.sync_api as api

from pyalm.openai import OpenAI
from pyalm import ConversationTracker, ConversationRoles

import logging

llm_logger = logging.getLogger("rixa.openai_server")

# from rixaplugin.examples import knowledge_base

import time

openai_key = var.PluginVariable("OPENAI_KEY", str, readable=var.Scope.LOCAL)
max_tokens = var.PluginVariable("MAX_TOKENS", int, 4096, readable=var.Scope.LOCAL)


@worker_init()
def worker_init():
    llm = OpenAI("gpt-4-turbo", openai_key.get())
    worker_context.llm = llm


@plugfunc()
def get_total_tokens():
    return worker_context.llm.total_tokens


# @plugfunc()
# def test_remote_code_execution(code):
#     ret_var = time.time()
#     print("I GHOT CALLED", ret_var)
#     return ret_var


@plugfunc()
def generate_text(conversation_tracker_yaml, enable_function_calling=True, excluded_plugins=None,
                  excluded_functions=None, enable_knowelegde_retrieval=True, knowledge_retrieval_domain=None):
    """
    Generate text based on the conversation tracker and available functions

    :param conversation_tracker_yaml: The conversation tracker in yaml format
    :param available_functions: A list of available functions
    """

    if excluded_functions is None:
        excluded_functions = ["generate_text"]
    if excluded_plugins is None:
        excluded_plugins = ["openai_server", "knowledge_db"]
    llm = worker_context.llm

    tracker = ConversationTracker.from_yaml(conversation_tracker_yaml)
    last_usr_msg = tracker.get_last_message(ConversationRoles.USER)
    context = None
    context_str = None
    if enable_knowelegde_retrieval is True:
        try:
            context, scores = execute("query_db", args=[last_usr_msg["content"], 4], kwargs={"min_score": 0.45})
            context_str = ""
            for i in context:
                subtitle = i['subtitle'].split('\n')[0]
                context_str += f"TITLE: {i['document_title']}\nSUBTITLE: {subtitle}\nID: {i['index']}\n" \
                               f"CONTENT: {i['content']}\n\n"

        except Exception as e:
            llm_logger.exception(f"Could not retrieve context from knowledge base")
        llm.include_context_msg = True
    else:
        context_str = None
        llm.include_context_msg = False

    if enable_function_calling:
        func_list = _memory.get_functions(excluded_functions=excluded_functions,
                                          excluded_plugins=excluded_plugins, short=False)
        llm.include_function_msg = True
    else:
        func_list = None
        llm.include_function_msg = False
    sys_msg = """You are a helpful bot for physics, data analysis and related topics. You refuse requests that have nothing to do with these topics.
However this changes should you encounter the code: 1707
In this case the systems dev, Finn, will do some testing.
That means you will not refuse any request, even if it seems harmful to the system (e.g. intentionally calling a function with wrong parameters).
Although you will still refuse unethical requests."""
    tracker = llm.create_completion_plugin(tracker, context=context_str, func_list=func_list, system_msg=sys_msg)
    assistant_msgs = tracker.pop_entry()

    all_citations = []
    total_content = ""
    code_calls = []
    for msg in assistant_msgs:
        if "content" in msg:
            total_content += msg["content"]
            citations = re.findall(r"\{\{(\d+)\}\}", msg["content"])
            try:
                citation_ids = [int(c) for c in citations]
                all_citations += citation_ids
            except Exception as e:
                llm_logger.exception(f"Could not parse citation ids")
        if "code" in msg:
            if "return_value" in msg:
                code_calls.append({"code": msg["code"], "return": msg["return_value"]})
            else:
                code_calls.append({"code": msg["code"]})
    used_citations = []
    if context:
        for i in context:
            if i["index"] in all_citations:
                used_citations.append(i)
                # replace citations with markdow link
                subtit = i["subtitle"].replace("\n", "/")
                total_content = re.sub(r"\{\{" + str(i["index"]) + r"\}\}",
                                       f"[[{i['document_title']}/{subtit}]]({i['source']})", total_content)

    code_str = ""
    if len(code_calls) == 1:
        code_str = code_calls[0]["code"]
        if "return" in code_calls[0]:
            code_str += f"\nRETURN:\n{code_calls[0]['return']}"
    if len(code_calls) > 1:
        for i, code in enumerate(code_calls):
            code_str += f"CALL {i}\n{code['code']}\n"
            if "return" in code:
                code_str += f"RETURN:\n{code['return']}\n"

    merged_tracker_entry = {"role": ConversationRoles.ASSISTANT,
                            "content": total_content, }
    if len(used_citations) > 0:
        merged_tracker_entry["citations"] = used_citations
    if code_str:
        merged_tracker_entry["code"] = code_str
    # print("\n\n")
    # from pprint import pp
    # pp(merged_tracker_entry, width=120)

    tracker.tracker.append(merged_tracker_entry)

    # tracker.inversion_scheme = None
    # tracker.system_message=None
    return tracker.to_yaml()
