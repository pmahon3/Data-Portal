"""Production ASGI entry: generated FastAPI app + observability shell.

Prefer this module over ``bundler_server.main:app``:

    uvicorn bundler_server.observability.app:app --host 0.0.0.0 --port 8080
"""

import logging
from bundler_server.main import app as _generated_app
from bundler_server.observability.bootstrap import setup_observability

app = setup_observability(_generated_app)

# Define the filter class
class ChecksFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        # Returns False if the log message contains the health endpoint path
        return "/health" not in record.getMessage() or "/metrics" not in record.getMessage()

# Apply the filter to hide health and metrics check logs from the uvicorn access logger
logging.getLogger("uvicorn.access").addFilter(ChecksFilter())
