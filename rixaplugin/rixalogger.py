import io
import linecache
import logging
import sys
import traceback


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

class RIXAFilter(logging.Filter):
    def __init__(self):
        super(RIXAFilter, self).__init__()
        self.session_id = None

    def filter(self, record):
        # Attach ID as attribute to log record. But memory may not be initialized yet
        if not self.session_id:
            try:
                from .memory import _memory
                self.session_id = _memory.ID[-4:]
            except ImportError:
                pass
        if self.session_id:
            record.session_id = self.session_id
        else:
            record.session_id = "NO_ID"

        return True


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

        if self.colormode == "html":
            log_fmt = self.FORMATS_HTML.get(record.levelno) + self.fmt_string + "</p>"
        elif self.colormode == "console":
            log_fmt = self.FORMATS_CONSOLE.get(record.levelno) + self.fmt_string + TerminalFormat.Reset
        else:
            log_fmt = self.fmt_string
        formatter = logging.Formatter(log_fmt, self.time_fmt)
        return formatter.format(record)


class JupyterLoggingHandler(logging.Handler):
    def __init__(self, max_messages=10):
        super().__init__()
        self.output_stream = io.StringIO()
        from .settings import LOG_FMT, LOG_TIME_FMT
        # self.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
        self.setFormatter(RIXAFormatter("html", LOG_FMT, LOG_TIME_FMT))
        # add rixafilter
        self.addFilter(RIXAFilter())
        self.messages = []
        self.max_messages = max_messages
        self.display_id = 'jupyter_logging_handler'  # Unique ID for the display object
        from IPython.display import display, update_display, HTML
        self.update_display = update_display
        self.HTML = HTML
        # Initial display with empty content, using the unique display_id
        display('', display_id=self.display_id)

    def emit(self, record):
        # Format the record and append it to the messages list
        with open("/home/finn/Fraunhofer/other stuff/network/a.txt", "a") as f:
            f.write(str(record.__dict__))
            f.write("\n\n\n")

        if record.levelno<10:
            return
        message = self.format(record)
        self.messages.append(message)

        # Ensure we only keep the last `max_messages` messages
        self.messages = self.messages[-self.max_messages:]

        # Write the truncated message list to the output stream
        self.output_stream.seek(0)
        self.output_stream.truncate()
        self.output_stream.write('\n'.join(self.messages))

        # Update the display with the new content
        self.update_display(self.HTML(self.output_stream.getvalue()), display_id=self.display_id)



def format_exception(exception, context_lines=2, without_color=False, limit=5, html=False):
    tracelist = traceback.extract_tb(exception.__traceback__, limit=limit)
    trace_string = '\033[48;2;80;30;27m'
    trace_string_colorless = ""
    for trace in tracelist[2:]:
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