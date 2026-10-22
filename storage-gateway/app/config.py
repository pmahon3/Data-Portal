"""Settings for the POSIX file service, read from the environment."""
import os
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    """
    :param root: Directory holding the governed files. Resource ``namespace/key`` maps to ``root/key``.
    :param namespace: The namespace this service serves; tokens must name it as their audience.
    :param jwks_url: Where the portal publishes the public key for its signed links.
    :param issuer: The ``iss`` claim the portal puts in its tokens.
    :param cors_origins: Browser origins allowed to call the service directly (uploads and downloads).
    :param chunk_size: Bytes read per chunk when streaming.
    """

    root: Path
    namespace: str
    jwks_url: str
    issuer: str = "inn-portal"
    cors_origins: list[str] = field(default_factory=list)
    chunk_size: int = 1024 * 1024

    @classmethod
    def from_env(cls) -> "Settings":
        origins = os.getenv("GATEWAY_CORS_ORIGINS", "")
        return cls(
            root=Path(os.environ["GATEWAY_ROOT"]).resolve(),
            namespace=os.environ["GATEWAY_NAMESPACE"],
            jwks_url=os.environ["GATEWAY_JWKS_URL"],
            issuer=os.getenv("GATEWAY_ISSUER", "inn-portal"),
            cors_origins=[o.strip() for o in origins.split(",") if o.strip()],
        )
