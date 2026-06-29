# coding: utf-8

"""Concrete API implementation: one ``BaseDefaultApi`` subclass for all routes.

Versioned paths (``/v1``, ``/v2``) and unversioned “current” paths share the same
domain logic for now; diverge per-method when v1/v2 behavior differs.
"""

from __future__ import annotations

import os

from fastapi import HTTPException
from fastapi.responses import JSONResponse, Response
from pydantic import StrictStr, ValidationError

from bundler_server.apis.default_api_base import BaseDefaultApi
from bundler_server.models.bundle import Bundle
from bundler_server.models.create_bundle_request import CreateBundleRequest
from bundler_server.models.health_response import HealthResponse

# Domain logic from ``bundler_core`` (library surface; see ``bundler_core/pyproject.toml``).
from bundler_core import (  # type: ignore[reportMissingImports]
    create_bundle_job as bundler_create_bundle_job,
    download_bundle_archive as bundler_download_bundle_archive,
    get_bundle_status as bundler_get_bundle_status,
    health as bundler_health,
)

STUB_MAX_URL_COUNT = int(os.environ.get("STUB_MAX_URL_COUNT", 64))


def _bundle_accepted_json(bundle: Bundle) -> JSONResponse:
    """Return the bundle body with HTTP **202** (contract / OpenAPI).

    The generated routes do not set ``status_code=202`` on the decorator. FastAPI
    then uses its default success code (**200**) when the handler returns a plain
    Pydantic model—so the implementation would not match the spec. Returning
    ``JSONResponse(..., status_code=202)`` sets the real status without editing
    generated ``default_api.py``.
    """
    return JSONResponse(
        status_code=202,
        content=bundle.model_dump(mode="json", by_alias=True),
    )


class DefaultApiImpl(BaseDefaultApi):
    """Registers as ``BaseDefaultApi.subclasses[0]`` for generated ``default_api`` routes.

    Method docstrings summarize **HTTP verb**, **path**, typical **status codes**, and
    response shape so you need not open ``apis/default_api.py`` or ``openapi.source.yaml``.
    """

    # -- health (v1 / v2 / current) ------------------------------------------

    async def get_health_v1(self) -> HealthResponse:
        """GET ``/v1/health``. **200** ``HealthResponse`` (service status)."""
        return await self._get_health_impl()

    async def get_health_v2(self) -> HealthResponse:
        """GET ``/v2/health``. **200** ``HealthResponse`` (service status)."""
        return await self._get_health_impl()

    async def get_health(self) -> HealthResponse:
        """GET ``/health`` (unversioned). **200** ``HealthResponse`` (service status)."""
        return await self._get_health_impl()

    async def _get_health_impl(self) -> HealthResponse:
        """Shared health handler: **200** body from ``bundler_health()``."""
        result = bundler_health()
        return HealthResponse(status=result.get("status"))

    # -- bundles POST --------------------------------------------------------

    async def create_bundle_v1(self, create_bundle_request: CreateBundleRequest) -> JSONResponse:  # type: ignore[override]
        """POST ``/v1/bundles`` (JSON ``CreateBundleRequest``). **202** ``Bundle`` accepted."""
        return await self._create_bundle_impl(create_bundle_request)

    async def create_bundle_v2(self, create_bundle_request: CreateBundleRequest) -> JSONResponse:  # type: ignore[override]
        """POST ``/v2/bundles`` (JSON ``CreateBundleRequest``). **202** ``Bundle`` accepted."""
        return await self._create_bundle_impl(create_bundle_request)

    async def create_bundle(self, create_bundle_request: CreateBundleRequest) -> JSONResponse:  # type: ignore[override]
        """POST ``/bundles`` (unversioned). **202** ``Bundle`` accepted."""
        return await self._create_bundle_impl(create_bundle_request)

    async def _create_bundle_impl(self, create_bundle_request: CreateBundleRequest) -> JSONResponse:
        """POST bundles — enqueue bundle job.

        **202** ``Bundle`` on success. **400** missing/invalid body or validation;
        **413** URL list over ``STUB_MAX_URL_COUNT``; **409** duplicate job (``KeyError``);
        **500** runtime/unknown errors
        **501** not implemented. OpenAPI validation may yield **422** before this handler runs.
        """
        if create_bundle_request is None:
            raise HTTPException(status_code=400, detail="Invalid request")
        try:
            if len(create_bundle_request.urls) > STUB_MAX_URL_COUNT:
                raise HTTPException(
                    status_code=413,
                    detail=f"Payload too large, max is {STUB_MAX_URL_COUNT} files",
                )
            raw = bundler_create_bundle_job(create_bundle_request)
        except ValidationError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except KeyError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except NotImplementedError:
            raise HTTPException(status_code=501, detail="Not implemented")
        except HTTPException as exc:
            raise exc
        except RuntimeError as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc
        return _bundle_accepted_json(Bundle.model_validate(raw))

    # -- bundle status GET ---------------------------------------------------

    async def get_bundle_v1(self, bundleId: StrictStr) -> JSONResponse:  # type: ignore[override]
        """GET ``/v1/bundles/{bundleId}``. **202** ``Bundle`` status; **404** unknown id."""
        return await self._get_bundle_impl(bundleId)

    async def get_bundle_v2(self, bundleId: StrictStr) -> JSONResponse:  # type: ignore[override]
        """GET ``/v2/bundles/{bundleId}``. **202** ``Bundle`` status; **404** unknown id."""
        return await self._get_bundle_impl(bundleId)

    async def get_bundle(self, bundleId: StrictStr) -> JSONResponse:  # type: ignore[override]
        """GET ``/bundles/{bundleId}`` (unversioned). **202** ``Bundle``; **404** unknown id."""
        return await self._get_bundle_impl(bundleId)

    async def _get_bundle_impl(self, bundleId: StrictStr) -> JSONResponse:
        """GET bundle by id — **202** ``Bundle`` from ``bundler_get_bundle_status``;
        **422** invalid ``bundleId`` (OpenAPI / Pydantic); **404** if missing; **500** runtime; **501** not implemented.
        """
        try:
            raw = bundler_get_bundle_status(bundleId)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except NotImplementedError:
            raise HTTPException(status_code=501, detail="Not implemented")
        except RuntimeError as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc
        return _bundle_accepted_json(Bundle.model_validate(raw))

    # -- download GET --------------------------------------------------------

    async def download_bundle_v1(self, bundleId: StrictStr) -> bytes:
        """GET ``/v1/bundles/{bundleId}/download``. **200** ``application/zip``; **202** not ready; **404**."""
        return await self._download_bundle_impl(bundleId)

    async def download_bundle_v2(self, bundleId: StrictStr) -> bytes:
        """GET ``/v2/bundles/{bundleId}/download``. **200** ``application/zip``; **202** not ready; **404**."""
        return await self._download_bundle_impl(bundleId)

    async def download_bundle(self, bundleId: StrictStr) -> bytes:
        """GET ``/bundles/{bundleId}/download`` (unversioned). **200** zip; **202** not ready; **404**."""
        return await self._download_bundle_impl(bundleId)

    async def _download_bundle_impl(self, bundleId: StrictStr):
        """GET bundle archive — **200** ``Response`` with zip bytes; **202** if bundle not ready;
        **422** invalid ``bundleId`` (OpenAPI / Pydantic); **404** unknown id; **500** other runtime errors; **501** not implemented.
        """
        try:
            body = bundler_download_bundle_archive(bundleId)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except NotImplementedError:
            raise HTTPException(status_code=501, detail="Not implemented")
        except RuntimeError as exc:
            if "not ready" in str(exc).lower():
                raise HTTPException(status_code=202, detail="Bundle not ready") from exc
            raise HTTPException(status_code=500, detail=str(exc)) from exc
        # Annotated as bytes in OpenAPI base; Response preserves application/zip.
        return Response(content=body, media_type="application/zip")
