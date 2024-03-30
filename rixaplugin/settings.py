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

config = AutoConfig()#Config(RepositoryEnv(os.path.join(config_dir, "config.ini")))
WORKING_DIRECTORY = os.path.abspath(config_dir)

DEBUG_MODE = config("DEBUG_MODE", default=False, cast=bool)

ALLOWED_PLUGIN_HOSTS = config("ALLOWED_HOSTS", default="localhost", cast=Csv())
"""List of domains which the plugin server serves. '*' means all connections will be accepted.
"""

logfile_path = config("LOG_LOC", default="log/main")
"""Where logfile is located. Without starting `/` it is considered relative to the working directory.
"""
LOG_FILE_TYPE = config("LOG_FILE_TYPE", default="txt", cast=Choices(["none", "html", "txt"]))
"""Either none, html or txt. None means no log files are created. html supports color formatting while. 
"""
if LOG_FILE_TYPE != "none" and logfile_path[0] != "/":
    logfile_path = os.path.abspath(os.path.join(config_dir, logfile_path + f".{LOG_FILE_TYPE}"))

DISABLED_LOGGERS = config("DISABLED_LOGGERS", cast=Csv(), default='')
"""Loggers that will be excluded on all outputs
"""

DISABLED_LOGGERS += ['daphne.http_protocol', 'daphne.server', 'daphne.ws_protocol', 'django.channels.server',
                     'asyncio', 'openai', "urllib3", "matplotlib", "sentence_transformers.SentenceTransformer"]
disabled_logger_conf = {i: {'level': 'WARNING'} for i in DISABLED_LOGGERS}

LOG_FMT = config("LOG_FMT",
                 # default="%(levelname)s:%(name)s \"%(message)s\" %(asctime)s-(File \"%(filename)s\", line %(lineno)d)"
default="%(levelname)s:%(name)s \"%(message)s\" (File \"%(filename)s\", line %(lineno)d)"
                 )
"""Format to be used for logging. See https://docs.python.org/3/library/logging.html#logrecord-attributes
There is an additional session_id attribute. It's behaviour is defined by LOG_UID_MODE
"""

MAX_LOG_SIZE = config("MAX_LOG_SIZE", default=16, cast=int)
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
    # 'filters': {
    #     'RIXAFilter': {
    #         '()': 'plugins.log_helper.RIXAFilter',
    #         "uid_mode": LOG_UID_MODE
    #     }
    # },
    'handlers': {
        'console': {
            'level': 'DEBUG',
            # 'filters': ['RIXAFilter'],
            'class': 'logging.StreamHandler',
            'formatter': 'RIXAConsole'
        },
        'file': {
            'class': 'logging.handlers.RotatingFileHandler',
            'maxBytes': MAX_LOG_SIZE * 1024,
            'backupCount': 2,
            'filename': logfile_path,
            'level': 'DEBUG',
            # 'filters': ['RIXAFilter'],
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
logging.config.dictConfig(LOGGING)