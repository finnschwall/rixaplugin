from enum import IntFlag
import asyncio

#export PYTHONASYNCIODEBUG=1




async def _supervisor(future):
    try:
        await future
        print("Supervision ok")
    except Exception as e:
        print("supervision failed")
        raise e
        # print(f"Supervision Error: {e}")


async def supervise_future(future):
    asyncio.create_task(_supervisor(future))


def identifier_from_signature(fname, args=[], kwargs={}):
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
