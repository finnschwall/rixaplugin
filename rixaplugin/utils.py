from enum import IntFlag
import asyncio
import logging
from . settings import DEBUG_MODE
task_superviser_log = logging.getLogger("task_superviser")

# export PYTHONASYNCIODEBUG=1


async def _supervisor(future, id=None):
    try:
        await future
    except Exception as e:
        task_superviser_log.exception(f"Error in unsupervised call" + (f" with id {id}" if id else ""))
        # print(f"Supervision Error: {e}")


async def supervise_future(future, id=None):
    """
    Supervise a future, log any exceptions.

    Used for plugin calls that are not awaited.
    :param future: Future to supervise
    :param id: Origin id (if available)
    """
    asyncio.create_task(_supervisor(future, id))


def identifier_from_signature(fname, args=[], kwargs={}):
    """
    Create a unique identifier from function signature.

    If debug mode is enabled, this returns a human-readable string, that allows to identify the function.
    This means the ID is not necessarily unique!
    :param fname:
    :param args:
    :param kwargs:
    :return: Unique identifier
    """
    if DEBUG_MODE:
        args_str = str(args)[:10]
        kwargs_str = str(kwargs)[:10]
        signature = f"{fname}({args_str}, {kwargs_str})"
        signature = signature+str(hash(signature))[1:5]
        return signature
    signature = fname
    for arg in args:
        signature += str(arg)
    if len(args) == 0:
        signature += "NOARGS"
    for k, v in kwargs.items():
        signature += str(k) + str(v)
    if len(kwargs) == 0:
        signature += "NOKWARGS"
    return hash(signature)
