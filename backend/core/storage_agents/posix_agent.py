import logging
from email.utils import parsedate_to_datetime
from urllib.parse import quote

import httpx

from core.services.storage_links import get_link_signer
from core.storage_agents.abstract_storage_agent import AbstractStorageAgent

logger = logging.getLogger('storage.posix')

# Lifetime of the tokens the backend uses for its own calls to the file service.
SERVICE_CALL_TTL_SECONDS = 60


class PosixStorageAgent(AbstractStorageAgent):
    """
    Storage agent for data on a POSIX machine, served by the portal's file service on that machine.

    The backend decides access and signs a short-lived token for each operation; the file service
    checks the token and reads or writes its own disk. One configured namespace stands in for an
    S3 bucket: resources are ``namespace/key``.
    """

    FLAVOUR = 'posix'
    CONFIG = {
        "instance_url": str,
        "namespace": str,
    }

    def __init__(self, instance_url: str, namespace: str):
        """
        :param instance_url: Base URL of the file service on the POSIX machine.
        :param namespace: Name used in resources, policies and the file tree for this instance.
        """
        super().__init__(instance_url.rstrip("/"))
        namespace = namespace.strip()
        if not namespace or "/" in namespace:
            raise ValueError("The POSIX namespace must be a single non-empty name without '/'.")
        self.namespace = namespace

    def connect(self):
        """Check the signing key is configured and the file service is reachable."""
        self._signer = get_link_signer()
        try:
            response = self._http().get(f"{self.instance_url}/v1/health")
        except httpx.HTTPError as e:
            logger.exception(f"POSIX file service unreachable at {self.instance_url}")
            self.close()
            raise ConnectionError(
                "Unable to reach the POSIX file service. Please verify that the URL is correct and the service is running."
            ) from e
        if response.status_code != 200:
            self.close()
            raise ConnectionError(
                f"The POSIX file service at {self.instance_url} is not healthy (HTTP {response.status_code})."
            )

    def fetch_all_buckets(self) -> list[str]:
        """Return the instance's namespace, which plays the role of a bucket."""
        return [self.namespace]

    def generate_access_link(
        self, resource: str, method: str, ttl: int, subject: str | None = None, grant: str | None = None
    ) -> tuple[list[str], list[str]]:
        """
        Generate a signed download or upload URL for one file.

        :param grant: Optional approval ID shared by every link issued for one approved request, so the
            file service uses one temporary user ID for all of them.
        """
        operation_by_access = {
            "read": "read",
            "write": "write",
        }
        operation = operation_by_access.get(method)
        if operation is None:
            raise ValueError(f"Unsupported access method {method!r}")

        self._check_resource(resource)
        token = self._signer.sign(self.namespace, resource, operation, ttl, subject=subject, grant=grant)
        url = f"{self._file_url(resource)}?{httpx.QueryParams(token=token)}"
        logger.debug("generate_access_link (%s): URL for %s", method, resource)
        return [url], [resource]

    def delete_object(self, resource: str, subject: str | None = None):
        """Delete a file identified by ``namespace/key``. Deleting a missing file succeeds."""
        response = self._service_call("DELETE", resource, "delete", subject=subject)
        if response.status_code not in (200, 204, 404):
            self._raise_for_status(response, resource)

    def delete_objects(self, resources: list[str]):
        """Delete files identified by ``namespace/key`` resource paths."""
        for resource in resources:
            self.delete_object(resource)

    def get_object_metadata(self, resource: str):
        """
        Return metadata for a file identified by ``namespace/key``, with the same keys as S3's
        ``head_object`` that callers use.
        """
        response = self._service_call("HEAD", resource, "stat")
        if response.status_code == 404:
            raise FileNotFoundError(f"No such file: {resource}")
        self._raise_for_status(response, resource)

        headers = response.headers
        metadata = {}
        if "content-length" in headers:
            metadata["ContentLength"] = int(headers["content-length"])
        if "etag" in headers:
            metadata["ETag"] = headers["etag"]
        if "last-modified" in headers:
            metadata["LastModified"] = parsedate_to_datetime(headers["last-modified"])
        if "content-type" in headers:
            metadata["ContentType"] = headers["content-type"]
        return metadata

    def _check_resource(self, resource: str):
        """Reject resources outside this namespace or with path segments that could escape it."""
        namespace, sep, key = resource.partition("/")
        if not sep or namespace != self.namespace:
            raise ValueError(f"Resource {resource!r} is not in namespace {self.namespace!r}")
        segments = key.split("/")
        if not key or "\x00" in key or any(s in ("", ".", "..") for s in segments):
            raise ValueError(f"Bad POSIX path: {resource!r}")

    def _file_url(self, resource: str) -> str:
        return f"{self.instance_url}/v1/files/{quote(resource, safe='/')}"

    def _service_call(self, http_method: str, resource: str, operation: str,
                      subject: str | None = None) -> httpx.Response:
        self._check_resource(resource)
        token = self._signer.sign(self.namespace, resource, operation, SERVICE_CALL_TTL_SECONDS, subject=subject)
        try:
            return self._http().request(
                http_method,
                self._file_url(resource),
                headers={"Authorization": f"Bearer {token}"},
            )
        except httpx.HTTPError as e:
            logger.exception(f"POSIX file service call failed ({http_method} {resource})")
            raise ConnectionError("Unable to reach the POSIX file service.") from e

    def _raise_for_status(self, response: httpx.Response, resource: str):
        if response.status_code in (401, 403):
            raise PermissionError(f"The POSIX file service refused the request for {resource}.")
        if response.status_code >= 400:
            raise RuntimeError(
                f"The POSIX file service returned HTTP {response.status_code} for {resource}."
            )

    def _http(self) -> httpx.Client:
        """
        The HTTP client, reopened if it was closed. Instance wrappers close their agent when they're
        garbage-collected while the instance manager still uses it; S3's client recovers the same way.
        """
        client = getattr(self, "_client", None)
        if client is None or client.is_closed:
            client = self._client = httpx.Client(timeout=httpx.Timeout(10.0))
        return client

    def close(self):
        client = getattr(self, "_client", None)
        if client is not None:
            client.close()

    def __str__(self):
        return f"PosixStorageAgent(instance_url={self.instance_url}, namespace={self.namespace})"
