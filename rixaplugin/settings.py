from decouple import Config, RepositoryEnv, Csv, Choices, AutoConfig
import os
import logging
import logging.config

from . import rixalogger

# DOC_BUILD = "BUILD_DOCS" in os.environ and os.environ["BUILD_DOCS"] == "True"
#
# try:
#     config_dir = os.environ["RIXA_WD"]
# except KeyError:
#     current_directory = os.getcwd()
#     files = os.listdir(current_directory)
#     if "config.ini" in files:
#         config_dir = current_directory
#     else:
#         raise Exception(
#             f"The folder '{current_directory}' from which you started the server does not seem to be a RIXA-like working directory."
#             f"Either change into a working dir or set the 'RIXA_WD' env var.")
#
# if not DOC_BUILD:
#     for dirs in ["plugins", "plugin_configurations", "log"]:
#         full_path = os.path.join(config_dir, dirs)
#         if not os.path.exists(full_path):
#             try:
#                 os.mkdir(full_path)
#             except Exception as e:
#                 print(e)
#                 raise Exception(f"Your working dir is missing the '{dirs}' folder. Automatic fixing has failed. "
#                                 f"Is the working dir read only?")
config_dir = "."

#Config(RepositoryEnv(os.path.join(config_dir, "config.ini")))


try:
    config_dir = os.environ["RIXA_WD"]
    config = Config(RepositoryEnv(os.path.join(config_dir, "config.ini")))
except KeyError:
    current_directory = os.getcwd()
    files = os.listdir(current_directory)
    if "config.ini" in files:
        config_dir = current_directory
        config = Config(RepositoryEnv(os.path.join(config_dir, "config.ini")))
    else:
        config_dir = os.path.abspath(config_dir)
        config = AutoConfig()
        import warnings
        warnings.warn("RIXA_WD not set. Using current directory as working directory.")
        # raise Exception(
        #     f"The folder '{current_directory}' from which you started the server does not seem to be a RIXA working directory."
        #     f"Either change into a working dir or set the 'RIXA_WD' env var.")
#
#
# WORKING_DIRECTORY = os.path.abspath(config_dir)



DEBUG = config("DEBUG_MODE", default=True, cast=bool)


ALLOW_NETWORK_RELAY = config("ALLOW_NETWORK_RELAY", default=True, cast=bool)
"""If there are servers A B and C, where B is this server, this setting controls if A can send messages to C through B,
and vice versa.
Usually this is only activated for the main server.
If activated on most/all servers, a decentralized system is possible (at cost of performance)."""

ALLOWED_PLUGIN_HOSTS = config("ALLOWED_HOSTS", default="localhost", cast=Csv())
"""List of domains which the plugin server serves. '*' means all connections will be accepted.
"""

logfile_path = config("LOG_LOC", default="log/main")
"""Where logfile is located. Without starting `/` it is considered relative to the working directory.
"""


PLUGIN_REGISTRY = config("PLUGIN_REGISTRY", default="/tmp/plugin_registry.json")

LOG_FILE_TYPE = config("LOG_FILE_TYPE", default="none", cast=Choices(["none", "html", "txt"]))
"""Either none, html or txt. None means no log files are created. html supports color formatting while. 
"""
if LOG_FILE_TYPE != "none" and logfile_path[0] != "/":
    logfile_path = os.path.abspath(os.path.join(config_dir, logfile_path + f".{LOG_FILE_TYPE}"))

DISABLED_LOGGERS = config("DISABLED_LOGGERS", cast=Csv(), default='')
"""Loggers that will be excluded on all outputs
"""

DISABLED_LOGGERS += ['daphne.http_protocol', 'daphne.server', 'daphne.ws_protocol', 'django.channels.server',
                     'asyncio', 'openai', "urllib3", "matplotlib", "sentence_transformers.SentenceTransformer",
                     "IPKernelApp","ipykernel","Comm","ipykernel.comm"]
disabled_logger_conf = {i: {'level': 'WARNING'} for i in DISABLED_LOGGERS}
# for i in [logging.getLogger(name) for name in logging.root.manager.loggerDict]:
#     if i.name in DISABLED_LOGGERS:
#         i.disabled = True

LOG_FMT = config("LOG_FMT",
                 # default="%(levelname)s:%(name)s \"%(message)s\" %(asctime)s-(File \"%(filename)s\", line %(lineno)d)"
default="%(levelname)s:%(name)s:%(session_id)s \"%(message)s\" (File \"%(filename)s\", line %(lineno)d)"
                 )
"""Format to be used for logging. See https://docs.python.org/3/library/logging.html#logrecord-attributes
There is an additional session_id attribute. It's behaviour is defined by LOG_UID_MODE
"""

MAX_LOG_SIZE = config("MAX_LOG_SIZE", default=200, cast=int)
"""Max file size in kb before new logfile will be created. Normally there are 2 backup logfiles.
1 kb~6-9 log messages for txt and ~4-7 for html
"""

CONSOLE_USE_COLORS = config("CONSOLE_USE_COLORS", default=True, cast=bool)
"""Wether to print in colors to console. On some systems that isn't supported in which case you will get flooded
with control sequences. Use this to deactivate colors in the console.
"""

LOG_TIME_FMT = config("LOG_TIME_FMT", default="%H:%M:%S")

logging.setLoggerClass(rixalogger.RIXALogger)
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'RIXAConsole': {
            '()': 'rixaplugin.rixalogger.RIXAFormatter',
            "colormode": "console" if CONSOLE_USE_COLORS else "none",
            "fmt_string": LOG_FMT,
            "time_fmt": LOG_TIME_FMT
        },
        'RIXAFile': {
            '()': 'plugins.log_helper.RIXAFormatter',
            "colormode": LOG_FILE_TYPE,
            "fmt_string": LOG_FMT,
            "time_fmt": LOG_TIME_FMT
        }
    },
    'filters': {
        'RIXAFilter': {
            '()': 'rixaplugin.rixalogger.RIXAFilter',
    #         "uid_mode": LOG_UID_MODE
        }
    },
    'handlers': {
        'console': {
            'level': 'WARNING',
            'filters': ['RIXAFilter'],
            'class': 'logging.StreamHandler',
            'formatter': 'RIXAConsole'
        },
        'file': {
            'class': 'logging.handlers.RotatingFileHandler',
            'maxBytes': MAX_LOG_SIZE * 1024,
            'backupCount': 2,
            'filename': logfile_path,
            'level': 'DEBUG',
            'filters': ['RIXAFilter'],
            'formatter': 'RIXAFile',
        } if LOG_FILE_TYPE != "none" else {'class': "logging.NullHandler"}
    },
    'loggers': {
        'root': {
            'handlers': ['console', 'file'] if LOG_FILE_TYPE != "none" else ["console"],
            'level': config("ROOT_LOG_LEVEL", default="DEBUG"),
            'class': "plugins.log_helper.RIXALogger"
        },
    }
}
LOGGING['loggers'].update(disabled_logger_conf)
logging.config.dictConfig(LOGGING)
