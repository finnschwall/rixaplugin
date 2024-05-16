from decouple import Config, RepositoryEnv, Csv, Choices, AutoConfig
import os
import logging.config
from rixaplugin.internal.rixalogger import RIXALogger as _RIXALogger
from .internal import rixalogger

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

# Config(RepositoryEnv(os.path.join(config_dir, "config.ini")))


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
        # import warnings
        # warnings.warn("RIXA_WD not set. Using current directory as working directory.")
        # raise Exception(
        #     f"The folder '{current_directory}' from which you started the server does not seem to be a RIXA working directory."
        #     f"Either change into a working dir or set the 'RIXA_WD' env var.")
#
#
# WORKING_DIRECTORY = os.path.abspath(config_dir)


DEBUG = config("DEBUG", default=True, cast=bool)

LOG_REMOTE_EXCEPTIONS_LOCALLY = config("LOG_EXCEPTIONS_LOCALLY", default=True, cast=bool)
"""Log exceptions (that occurred locally) but are meant for remote plugins to the local log stream
"""

ACCEPT_REMOTE_PLUGINS = config("ACCEPT_REMOTE_PLUGINS", default=2, cast=int)
"""Whether or not to retrieve remote plugins.
Usually set to true for servers and to false for clients.
Only activate for clients when remote calling other plugins is required for your plugin code.
0: Deny, 1 Allow, 2 automatic
"""

ALLOW_NETWORK_RELAY = config("ALLOW_NETWORK_RELAY", default=False, cast=bool)
"""If there are servers A B and C, where B is this server, this setting controls if A can send messages to C through B,
and vice versa.
Usually this is only activated for the main server.
This also controls whether this instance sends infos on connected plugins to newly connected instances.
If activated on most/all servers, a decentralized system is possible (at cost of performance. Also kinda buggy as of now)."""

ALLOWED_PLUGIN_HOSTS = config("ALLOWED_HOSTS", default="localhost", cast=Csv())
"""List of domains which the plugin server serves. '*' means all connections will be accepted.
"""

logfile_path = config("LOG_LOC", default="log/main")
"""Where logfile is located. Without starting `/` it is considered relative to the working directory.
"""

MAKE_REMOTES_IMPORTABLE = config("MAKE_REMOTES_IMPORTABLE", default=True, cast=bool)

PLUGIN_REGISTRY = config("PLUGIN_REGISTRY", default="/tmp/plugin_registry.json")

DEFAULT_MAX_WORKERS = config("DEFAULT_MAX_WORKERS", default=4, cast=int)
"""Default number of worker threads for a plugin server. This is the number of threads or processes that can execute plugin code.
"""

LOG_FILE_TYPE = config("LOG_FILE_TYPE", default="none", cast=Choices(["none", "html", "txt"]))
"""Either none, html or txt. None means no log files are created. html supports color formatting while. 
"""
if LOG_FILE_TYPE != "none" and logfile_path[0] != "/":
    logfile_path = os.path.abspath(os.path.join(config_dir, logfile_path + f".{LOG_FILE_TYPE}"))

DISABLED_LOGGERS = config("DISABLED_LOGGERS", cast=Csv(), default='')
"""Loggers that will be excluded on all outputs
"""

DISABLED_LOGGERS += ['daphne.http_protocol', 'daphne.server', 'daphne.ws_protocol', 'django.channels.server',
                    'openai', "urllib3", "matplotlib", "sentence_transformers.SentenceTransformer",
                     "IPKernelApp", "ipykernel", "Comm", "ipykernel.comm", "httpcore", "httpx",
                     "Comm"]
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

GLOBAL_LOG_LEVEL = config("GLOBAL_LOG_LEVEL", default="INFO")
RIXA_LOG_LEVEL = config("RIXA_LOG_LEVEL", default="DEBUG")

USE_RIXA_LOGGING = config("USE_RIXA_LOGGING", default=True, cast=bool)

if USE_RIXA_LOGGING:
    logging.setLoggerClass(_RIXALogger)
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'RIXAConsole': {
            '()': 'rixaplugin.internal.rixalogger.RIXAFormatter',
            "colormode": "console" if CONSOLE_USE_COLORS else "none",
            "fmt_string": LOG_FMT,
            "time_fmt": LOG_TIME_FMT
        },
        'RIXAFile': {
            '()': 'rixaplugin.internal.rixalogger.RIXAFormatter',
            "colormode": LOG_FILE_TYPE,
            "fmt_string": LOG_FMT,
            "time_fmt": LOG_TIME_FMT
        }
    },
    'filters': {
        'RIXAFilter': {
            '()': 'rixaplugin.internal.rixalogger.RIXAFilter',
            #         "uid_mode": LOG_UID_MODE
        }
    },
    'handlers': {
        'console': {
            'level': GLOBAL_LOG_LEVEL,
            'filters': ['RIXAFilter'],
            'class': 'logging.StreamHandler',
            'formatter': 'RIXAConsole'
        },
        'file': {
            'class': 'logging.handlers.RotatingFileHandler',
            'maxBytes': MAX_LOG_SIZE * 1024,
            'backupCount': 2,
            'filename': logfile_path,
            'level': GLOBAL_LOG_LEVEL,
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
if USE_RIXA_LOGGING:
    LOGGING['loggers'].update(disabled_logger_conf)
    logging.config.dictConfig(LOGGING)
    rixa_logger = logging.getLogger("rixa")
    rixa_logger.setLevel(RIXA_LOG_LEVEL)
