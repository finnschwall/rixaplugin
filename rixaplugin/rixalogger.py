import logging
import sys


class TerminalFormat:
    # just colors
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    STANDARDTEXT = "\033[38;2;255;255;255m"
    # End colored text
    END = '\033[0m'
    NC = '\x1b[0m'  # No Color

    # format stuff
    Bold = "\x1b[1m"
    Dim = "\x1b[2m"
    Italic = "\x1b[3m"
    Underlined = "\x1b[4m"
    Blink = "\x1b[5m"
    Reverse = "\x1b[7m"
    Hidden = "\x1b[8m"
    # Reset part
    Reset = "\x1b[0m"
    Reset_Bold = "\x1b[21m"
    Reset_Dim = "\x1b[22m"
    Reset_Italic = "\x1b[23m"
    Reset_Underlined = "\x1b[24"
    Reset_Blink = "\x1b[25m"
    Reset_Reverse = "\x1b[27m"
    Reset_Hidden = "\x1b[28m"

    @staticmethod
    def rgb(r, g, b, foreground=True, html=False, invert=False):
        if html:
            if invert:
                x = [r, g, b]
                x = [255 - i for i in x]
            return f"<p style='color:rgb({x[0]}, {x[1]}, {x[2]})'>"
        ctrl = "38" if foreground else "48"
        return f"\033[{ctrl};2;{r};{g};{b}m"


class RIXALogger(logging.Logger):
    def __init__(self, *args, **kwargs):
        super(RIXALogger, self).__init__(*args, **kwargs)

    def log_exception(self):
        exc_info = sys.exc_info()
        sinfo = None

        try:
            fn, lno, func, sinfo = self.findCaller(False, 3)
        except ValueError:  # pragma: no cover
            fn, lno, func = "(unknown file)", 0, "(unknown function)"
        if exc_info:
            if isinstance(exc_info, BaseException):
                exc_info = (type(exc_info), exc_info, exc_info.__traceback__)
        record = self.makeRecord(self.name, logging.WARNING, fn, lno, "Exception logged: ", None, None, func,
                                 {"is_exception": True, "exc": exc_info[1]}, sinfo)
        self.handle(record)


def rgb_to_html(x, invert=False):
    if invert:
        x = [255 - i for i in x]
    return f"<p style='color:rgb({x[0]}, {x[1]}, {x[2]})'>"


def format_exception(exception, context_lines=2, without_color=False, limit=5, html=False):
    tracelist = traceback.extract_tb(exception.__traceback__, limit=limit)
    trace_string = '\033[48;2;80;30;27m'
    trace_string_colorless = ""
    for trace in tracelist:
        filename = trace.filename
        line_number = trace.lineno

        lines = linecache.getlines(filename)
        start_line = max(line_number - context_lines, 1)
        end_line = min(line_number + context_lines, len(lines))
        code_area_lines = lines[start_line - 1:end_line]
        code_area = ''
        code_area_colorless = ""

        for i, x in enumerate(code_area_lines):
            if "\n" in x:
                x = x[:-1]
            if i == line_number - start_line:
                code_area += TerminalFormat.rgb(255, 63, 5, False)
            code_area += f"{TerminalFormat.rgb(10, 144, 72)}{start_line + i}{TerminalFormat.STANDARDTEXT} {x}" + "\n"
            code_area_colorless += f"{start_line + i} {x}" + "\n"
            if i == line_number - start_line:
                code_area += '\033[48;2;80;30;27m'

        loc_msg = f"\nIn {filename}:{line_number}\n"
        trace_string += TerminalFormat.Bold + loc_msg + TerminalFormat.Reset_Bold + code_area
        trace_string_colorless += loc_msg + code_area_colorless
    exc_msg = f"{type(exception).__name__}: {exception}"
    trace_string += exc_msg
    trace_string_colorless += exc_msg
    if without_color:
        return trace_string_colorless

    trace_lines = trace_string.split("\n")
    trace_lines_colorless = trace_string_colorless.split("\n")
    lens = [len(x) for x in trace_lines_colorless]
    max_len = max(lens)
    for i, x in enumerate(trace_lines):
        trace_lines[i] = x + " " * (max_len - lens[i] + 2)
    trace_string = "\n".join(trace_lines)

    return trace_string + TerminalFormat.NC


class RIXAFormatter(logging.Formatter):
    DEBUG = [51, 204, 204]
    INFO = [0, 255, 0]
    WARNING = [204, 204, 0]
    ERROR = [255, 0, 102]
    CRITICAL = [255, 0, 0]

    def __init__(self, colormode, fmt_string, time_fmt):
        super().__init__()
        self.colormode = colormode
        self.fmt_string = fmt_string
        self.time_fmt = time_fmt

    FORMATS_CONSOLE = {
        logging.DEBUG: TerminalFormat.rgb(*DEBUG),
        logging.INFO: TerminalFormat.rgb(*INFO),
        logging.WARNING: TerminalFormat.rgb(*WARNING),
        logging.ERROR: TerminalFormat.rgb(*ERROR),
        logging.CRITICAL: TerminalFormat.rgb(*CRITICAL)
    }
    FORMATS_HTML = {
        logging.DEBUG: rgb_to_html(DEBUG),
        logging.INFO: rgb_to_html(INFO),
        logging.WARNING: rgb_to_html(WARNING),
        logging.ERROR: rgb_to_html(ERROR),
        logging.CRITICAL: rgb_to_html(CRITICAL)
    }

    def format(self, record):
        # formatter = logging.Formatter(self.fmt_string, self.time_fmt)
        # return formatter.format(record)
        is_exception = getattr(record, "is_exception", 0)
        if is_exception:
            print(is_exception)

        if is_exception:
            exc = getattr(record, "exc", 0)
            # exc = record.exc_info[1]

            if self.colormode == "html":
                exc_msg = format_exception(exc, html=True)
                record.msg = record.msg.replace("\n", "<br>")
                col = self.FORMATS_HTML.get(record.levelno)
                res = "</p>"
                newline = "<br>"
            elif self.colormode == "console":
                exc_msg = format_exception(exc)
                col = self.FORMATS_CONSOLE.get(record.levelno)
                res = TerminalFormat.NC
                newline = "\n"
            else:
                exc_msg = format_exception(exc, without_color=True)
                col = ""
                res = ""
                newline = "\n"
            custom_msg = record.msg
            record.msg = exc_msg
            log_fmt = col + custom_msg + res + "%(message)s" + newline + col + "-------" + \
                      newline + "%(levelname)s %(session_id)s-%(asctime)s-%(name)s-(File \"%(pathname)s\", line %(lineno)d)" + res
            formatter = logging.Formatter(log_fmt, '%a %H:%M:%S')
            return formatter.format(record)

        if self.colormode == "html":
            log_fmt = self.FORMATS_HTML.get(record.levelno) + self.fmt_string + "</p>"
        elif self.colormode == "console":
            log_fmt = self.FORMATS_CONSOLE.get(record.levelno) + self.fmt_string + TerminalFormat.Reset
        else:
            log_fmt = self.fmt_string
        formatter = logging.Formatter(log_fmt, self.time_fmt)
        return formatter.format(record)



