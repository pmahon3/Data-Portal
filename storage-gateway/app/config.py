"""Read the POSIX file service's settings from the environment."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


# A file only the data owner can read. The access broker writes it; the web service refuses to start if it
# can read it (that would mean it isn't isolated from the data).
CANARY = ".gateway-canary"
OPEN_BATCH = 64  # files of a multi-file download opened per request to the access broker (one process there)


@dataclass(frozen=True)
class Settings:
    """
    The file service's settings.

    - ``root``: directory holding the governed files. Resource ``namespace/key`` maps to ``root/key``.
    - ``namespace``: the namespace this service serves; tokens must name it as their audience.
    - ``jwks_url``: where the portal publishes the public key for its signed links.
    - ``bundle_list_url``: where the portal serves approved file lists (``/{grant}`` is appended); by
      default beside ``jwks_url``.
    - ``issuer``: the ``iss`` claim the portal puts in its tokens.
    - ``cors_origins``: browser origins allowed to call the service directly (uploads and downloads).
    - ``chunk_size``: bytes read per chunk when streaming.
    - ``broker_socket``: the access broker's socket. When set, every file operation goes through
      the access broker and this service can't read the data itself.
    - ``require_isolation``: refuse to start without an access broker (set in the deployed container).
    - ``shared_account``: run without administrator access (``GATEWAY_ACCESS=shared-account``): this service is
      one ordinary account that can read and write the data, and the portal's links alone decide
      access.
    - ``max_downloads``: multi-file downloads streaming at once; extra ones wait for a slot.
    - ``download_wait_seconds``: how long an extra download waits before it's told to retry (503).
    - ``max_bundle_files``: the most files one multi-file download may list.
    - ``state_dir``: a folder this service can write to, for state kept across restarts (checksums of
      files already sent); without one, that state is kept in memory.
    """

    root: Path
    namespace: str
    jwks_url: str
    issuer: str = "inn-portal"
    cors_origins: list[str] = field(default_factory=list)
    chunk_size: int = 1024 * 1024
    broker_socket: str | None = None
    require_isolation: bool = False
    shared_account: bool = False
    bundle_list_url: str = ""
    max_downloads: int = 8
    download_wait_seconds: int = 300
    max_bundle_files: int = 200_000
    state_dir: Path | None = None

    @classmethod
    def from_env(cls) -> Settings:
        """Read the settings from ``GATEWAY_*`` environment variables."""
        origins = os.getenv("GATEWAY_CORS_ORIGINS", "")
        root = Path(os.environ["GATEWAY_ROOT"]).resolve()
        namespace = os.environ["GATEWAY_NAMESPACE"]
        jwks_url = os.environ["GATEWAY_JWKS_URL"]
        bundle_list_url = os.getenv("GATEWAY_BUNDLE_LIST_URL")
        if not bundle_list_url:
            # Example: "https://portal/api/v0.1/storage-links/jwks.json" -> ".../storage-links/bundles"
            bundle_list_url = jwks_url.rsplit("/", 1)[0] + "/bundles"
        state_dir = None
        if os.getenv("GATEWAY_STATE_DIR"):
            state_dir = Path(os.environ["GATEWAY_STATE_DIR"])
        return cls(
            root=root,
            namespace=namespace,
            jwks_url=jwks_url,
            issuer=os.getenv("GATEWAY_ISSUER", "inn-portal"),
            cors_origins=[o.strip() for o in origins.split(",") if o.strip()],
            broker_socket=os.getenv("GATEWAY_BROKER_SOCKET") or None,
            require_isolation=os.getenv("GATEWAY_REQUIRE_ISOLATION", "").lower() in {"1", "true", "yes"},
            shared_account=os.getenv("GATEWAY_ACCESS", "user-per-approval") == "shared-account",
            bundle_list_url=bundle_list_url,
            max_downloads=int(os.getenv("GATEWAY_MAX_DOWNLOADS", "8")),
            download_wait_seconds=int(os.getenv("GATEWAY_DOWNLOAD_WAIT_SECONDS", "300")),
            max_bundle_files=int(os.getenv("GATEWAY_MAX_BUNDLE_FILES", "200000")),
            state_dir=state_dir,
        )
