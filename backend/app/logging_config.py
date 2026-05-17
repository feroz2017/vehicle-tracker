"""
Structured JSON logging for the vehicle tracker backend.

Replaces Python's default unstructured format:
    2026-05-17 13:22:01 INFO Fetched 23 vehicles

With queryable JSON events:
    {"ts": "2026-05-17T13:22:01Z", "level": "INFO", "service": "worker",
     "msg": "fetch_cycle_complete", "vehicle_count": 23, "duration_ms": 412}

Usage:
    from app.logging_config import setup_logging
    setup_logging()                          # call once, before any logger.xxx()

    logger = logging.getLogger(__name__)
    logger.info("fetch_cycle_complete", extra={"vehicle_count": 23, "duration_ms": 412})
"""
import json
import logging
import time


# LogRecord fields that are Python internals — excluded from the JSON output
# to avoid noise. Caller-supplied extra= fields are passed through unmodified.
_SKIP_FIELDS = frozenset({
    "msg", "args", "levelname", "levelno", "pathname", "filename", "module",
    "exc_info", "exc_text", "stack_info", "lineno", "funcName", "created",
    "msecs", "relativeCreated", "thread", "threadName", "processName",
    "process", "name", "message", "taskName",
})


class JSONFormatter(logging.Formatter):
    """
    Formats each log record as a single JSON line.

    Core fields always present: ts, level, service, msg.
    Any extra= dict passed to the logger call is merged in at the top level:

        logger.info("my_event", extra={"route_id": "3", "count": 7})
        → {"ts": "...", "level": "INFO", "service": "worker",
           "msg": "my_event", "route_id": "3", "count": 7}
    """

    def format(self, record: logging.LogRecord) -> str:
        entry: dict = {
            "ts":      time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(record.created)),
            "level":   record.levelname,
            "service": record.name,
            "msg":     record.getMessage(),
        }

        # Merge any caller-supplied extra fields
        for key, val in record.__dict__.items():
            if key not in _SKIP_FIELDS:
                entry[key] = val

        # Include formatted exception if present
        if record.exc_info:
            entry["exception"] = self.formatException(record.exc_info)

        # default=str handles non-serialisable values (e.g. Exceptions, Paths)
        return json.dumps(entry, default=str)


def setup_logging(level: int = logging.INFO) -> None:
    """
    Install the JSON formatter on the root logger.

    Call once at process startup — before any logger.xxx() calls.
    All subsequent loggers (including third-party libraries) inherit it.
    """
    handler = logging.StreamHandler()
    handler.setFormatter(JSONFormatter())

    root = logging.getLogger()
    root.handlers = []        # remove any handlers basicConfig may have added
    root.addHandler(handler)
    root.setLevel(level)
