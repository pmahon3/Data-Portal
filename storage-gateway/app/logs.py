"""Keeps signed links out of the logs: a logged link is a usable link until it expires."""
import logging
import re

_TOKEN = re.compile(r"(?i)([?&]token=)[^&\s\"]*")


def redact_tokens(text: str) -> str:
    """Replace the value of any ``token`` query parameter."""
    return _TOKEN.sub(r"\1[redacted]", text)


class RedactTokens(logging.Filter):
    """Redact tokens from a record's message and arguments (uvicorn's access log passes the path as an argument)."""

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            record.msg = redact_tokens(record.msg)
        if isinstance(record.args, tuple):
            record.args = tuple(redact_tokens(a) if isinstance(a, str) else a for a in record.args)
        return True


def install_token_redaction() -> None:
    """Attach the filter to the loggers that see request paths."""
    for name in ("uvicorn.access", "uvicorn.error", "storage-gateway"):
        logging.getLogger(name).addFilter(RedactTokens())
