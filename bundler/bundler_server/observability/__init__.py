"""Hand-owned observability shell around the generated FastAPI app.

Ops surfaces (``/metrics``, ``/actuator/*``) live here so they stay out of
``openapi.source.yaml`` and are not wiped by OpenAPI Generator regenerations.
"""

from bundler_server.observability.bootstrap import setup_observability

__all__ = ["setup_observability"]
