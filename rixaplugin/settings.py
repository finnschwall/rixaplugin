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
WORKING_DIRECTORY = os.path.abspath(config_dir)

DEFAULT_PLUGIN_SERVER_PORT = config("DEFAULT_PLUGIN_SERVER_PORT", default=15000, cast=int)
"""
Default port on which the plugin server will listen.
"""

USE_AUTH_SYSTEM = config("USE_AUTH_SYSTEM", default=True, cast=bool)
AUTH_KEY_LOC = config("AUTH_KEY_LOC", default=None)
if not AUTH_KEY_LOC:
    AUTH_KEY_LOC = os.path.join(WORKING_DIRECTORY, "auth_keys")


DEBUG = config("DEBUG", default=True, cast=bool)
VERBOSE_REQUEST_ID = config("VERBOSE_REQUEST_ID", default=False, cast=bool)
"""Turns the request id from a hash to a readable string. This is useful for debugging but will lead to collisions.
"""

PLUGIN_DEFAULT_PORT = config("PLUGIN_SERVER_PORT", default=15000, cast=int)
"""
Port to which plugin system will bind to by default.
Not used outside of RIXA webserver or CLI.
"""
PLUGIN_DEFAULT_ADDRESS = config("PLUGIN_CLIENT_ADDRESS", cast=str, default="localhost")
"""
Default to which plugin system will connect/listen to.
Not used outside of RIXA webserver or CLI.
"""
AUTO_CONNECTIONS = config("AUTO_CONNECTIONS", default=None, cast=Csv())
"""
A list of addresses to which the plugin system will try to connect to on startup.

Format: "address:port-tag"
The tag is optional and can be used to automatically assign the plugin to a certain group.aaa
"""

TMP_DATA_LOG_FOLDER = config("TMP_DATA_LOG_FOLDER", default="/tmp/rixa_data_log")
"""
Folder for api.datalog_to_tmp
"""

AUTO_IMPORT_PLUGINS = config("AUTO_IMPORT_PLUGINS", cast=Csv(), default='')
"""
List of plugins to be imported on startup from a package.
Use the full path to the plugin e.g. for using the math plugin from rixaplugin.default_plugins use "rixaplugin.default_plugins.math".

These plugins will all inherit the settings of the importing process.
"""

AUTO_IMPORT_PLUGINS_PATHS = config("AUTO_IMPORT_PLUGINS_PATHS", cast=Csv(), default='')
"""
List of paths to be searched for plugins to be imported on startup.

Can point to a folder or a .py file.
These plugins will all inherit the settings of the importing process.
"""

AUTO_APPLY_TAGS = config("AUTO_APPLY_TAGS", cast=Csv(), default='')
"""
List of tags-plugin pairs to be applied on startup. Will be applied last i.e. after connecting to other plugins.
Does not apply to plugins that are manually imported or to connections that are manually established.
"""


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

MAX_QUEUE_SIZE = config("MAX_QUEUE_SIZE", default=3, cast=int)
"""Maximum number of tasks in the worker pools. Submitting after will raise an exception."""

LOG_PROCESSPOOL = config("LOG_PROCESSPOOL", default=False, cast=bool)
"""If true this will write all processpool activity into WORKING_DIRECTORY/log/processpool.csv
Specifically it will log when a new task is started and when it is finished. It will additionally add the current queue size and number of active workers.
"""

LOG_FILE_TYPE = config("LOG_FILE_TYPE", default="none", cast=Choices(["none", "html", "txt"]))
"""Either none, html or txt. None means no log files are created. html supports color formatting while. 
"""

if LOG_FILE_TYPE != "none" and logfile_path[0] != "/":
    logfile_path_alternate = os.path.abspath(os.path.join(config_dir, logfile_path + f"ALTERNATE.{LOG_FILE_TYPE}"))
    logfile_path = os.path.abspath(os.path.join(config_dir, logfile_path + f".{LOG_FILE_TYPE}"))
DISABLED_LOGGERS = config("DISABLED_LOGGERS", cast=Csv(), default='')
"""Loggers that will be excluded on all outputs
"""

DISABLED_LOGGERS += ['daphne.http_protocol', 'daphne.server', 'daphne.ws_protocol',
                    'openai', "urllib3", "matplotlib", "sentence_transformers.SentenceTransformer",
                     "IPKernelApp", "ipykernel", "Comm", "ipykernel.comm", "httpcore", "httpx",
                     "Comm"]
disabled_logger_conf = {i: {'level': 'WARNING'} for i in DISABLED_LOGGERS}

REDIRECTED_LOGGERS = config("REDIRECTED_LOGGERS", cast=Csv(), default='')
"""Loggers mentioned here will be sent to a separate file. Useful to e.g. separate django logs from plugin logs.
"""
REDIRECTED_LOGGERS += ["django.request", "django.security" ,"django.security.DisallowedHost", 'django.channels.server']

redirected_logger_conf = {i: {'handlers': ['file_alternate'] if LOG_FILE_TYPE != "none" else ["console"],
                              'propagate': False} for i in REDIRECTED_LOGGERS}
# for i in [logging.getLogger(name) for name in logging.root.manager.loggerDict]:
#     if i.name in DISABLED_LOGGERS:
#         i.disabled = True

LOG_FMT = config("LOG_FMT",
                 # default="%(levelname)s:%(name)s \"%(message)s\" %(asctime)s-(File \"%(filename)s\", line %(lineno)d)"
                 default="""%(asctime)s-%(name)s-%(levelname)s '%(message)s' (File "%(pathname)s", line %(lineno)d)"""
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

LOG_TIME_FMT = config("LOG_TIME_FMT", default="%H:%M:%S-%d.%m")

GLOBAL_LOG_LEVEL = config("GLOBAL_LOG_LEVEL", default="INFO")
RIXA_LOG_LEVEL = config("RIXA_LOG_LEVEL", default="DEBUG")

USE_RIXA_LOGGING = config("USE_RIXA_LOGGING", default=True, cast=bool)

FUNCTION_CALL_TIMEOUT = config("FUNCTION_CALL_TIMEOUT", default=60, cast=int)
"""Timeout for function calls in seconds. After this time an exception will be raised.
Multiple occurences can lead to a plugin being marked as offline and hence be disabled.

Also: Try to avoid timing out. It potentially leads to a plethora of error messages as everything along the call chain
will subsequently time out too. All intermediate instances may raise some sort of error."""

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
        } if LOG_FILE_TYPE != "none" else {'class': "logging.NullHandler"},
        'file_alternate': {
            'class': 'logging.handlers.RotatingFileHandler',
            'maxBytes': MAX_LOG_SIZE * 1024,
            'backupCount': 2,
            'filename': logfile_path_alternate,
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
    LOGGING['loggers'].update(redirected_logger_conf)
    logging.config.dictConfig(LOGGING)
    rixa_logger = logging.getLogger("rixa")
    rixa_logger.setLevel(RIXA_LOG_LEVEL)
