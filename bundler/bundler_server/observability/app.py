"""Production ASGI entry: generated FastAPI app + observability shell.

Prefer this module over ``bundler_server.main:app``:

    uvicorn bundler_server.observability.app:app --host 0.0.0.0 --port 8080
"""

from bundler_server.main import app as _generated_app
from bundler_server.observability.bootstrap import setup_observability

app = setup_observability(_generated_app)
