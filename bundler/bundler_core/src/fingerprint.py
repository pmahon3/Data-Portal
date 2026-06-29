from __future__ import annotations

from hashlib import sha256
from urllib.parse import parse_qsl, urlsplit, urlunsplit

from bundler_core.models import CreateBundleRequest

_VOLATILE_QUERY_KEYS = {
    "x-amz-algorithm",
    "x-amz-credential",
    "x-amz-date",
    "x-amz-expires",
    "x-amz-security-token",
    "x-amz-signature",
    "x-amz-signedheaders",
    "expires",
    "signature",
    "token",
}


def _normalize_url_for_key(url: str) -> str:
    """Return a canonical URL string for dedupe key generation.

    Normalization trims whitespace, lowercases scheme/netloc, removes known
    volatile signing query params (for example presign signatures and expiry),
    and sorts remaining query items to stabilize ordering.
    """
    parts = urlsplit(url.strip())
    filtered_query = sorted(
        (k, v)
        for k, v in parse_qsl(parts.query, keep_blank_values=True)
        if k.lower() not in _VOLATILE_QUERY_KEYS
    )
    canonical_query = "&".join(f"{k}={v}" for k, v in filtered_query)
    return urlunsplit(
        (
            parts.scheme.lower(),
            parts.netloc.lower(),
            parts.path,
            canonical_query,
            "",
        )
    )


def _bundle_key(request: CreateBundleRequest, *, compression_version: str = "v1") -> str:
    """Build a deterministic bundle fingerprint from request semantics.

    The key hashes folder name, compression settings, compression version, and
    normalized URLs. Equivalent URL lists (different order or volatile presign
    params) resolve to the same key.
    """
    normalized_urls = sorted(_normalize_url_for_key(url) for url in request.urls)
    folder_name = (request.folder_name or "").strip()
    material = "\n".join(
        [
            f"folder={folder_name}",
            f"compression={request.compression}",
            f"compression_version={compression_version}",
            "urls:",
            *normalized_urls,
        ]
    )
    return sha256(material.encode("utf-8")).hexdigest()
