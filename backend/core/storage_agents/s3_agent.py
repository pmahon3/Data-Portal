import logging
import os
from typing import List, Optional, Tuple

import boto3
from botocore.config import Config
from botocore.exceptions import EndpointConnectionError

from core.storage_agents.abstract_storage_agent import AbstractStorageAgent

logger = logging.getLogger('storage.s3')

def _bucket_access_level_enabled() -> bool:
    """True only for the string 'true' (production). 'false' and unset are false."""
    return os.environ.get("BUCKET_ACCESS_LEVEL", "").strip().lower() in {"1", "true", "yes"}

class S3StorageAgent(AbstractStorageAgent):
    FLAVOUR = 's3'
    CONFIG = {
        "instance_url": str,
        "aws_access_key_id": str,
        "aws_secret_access_key": str
    }

    # ensure CORS only applies once
    _cors_enabled = False

    def __init__(self,
                 instance_url: str,
                 aws_access_key_id: str,
                 aws_secret_access_key: str,
                 region_name: Optional[str] = None):
        super().__init__(instance_url)
        self.aws_access_key_id = aws_access_key_id
        self.aws_secret_access_key = aws_secret_access_key
        self.region_name = region_name.strip() if region_name and region_name.strip() else None

    def connect(self):
        try:
            self.s3_client = boto3.client(
                's3',
                endpoint_url=self.instance_url,
                aws_access_key_id=self.aws_access_key_id,
                aws_secret_access_key=self.aws_secret_access_key,
                config=Config(signature_version="s3v4"),
                region_name=self.region_name # pass in region name or None
            )

            # boto3 is lazy and doesn't throw an error until the client is actually used
            self.s3_client.list_buckets()

        # Map technical S3/connection errors to user-friendly exceptions.
        # Detailed diagnostic are logged within the storage agent.
        # Reference: https://docs.aws.amazon.com/AmazonS3/latest/API/ErrorResponses.html
        except Exception as e:
            # Handle botocore specific exceptions
            logger.error(f"Failed to initialize S3 client: {e}", exc_info=True)

            if isinstance(e, EndpointConnectionError):
                raise ConnectionError(
                    "Unable to reach the storage server. Please verify that the endpoint URL is correct and your network connection is stable."
                ) from e

            # Attempt to extract the AWS error code; fall back to 'Unknown'
            try:
                error_code = e.response.get('Error', {}).get('Code', 'Unknown')
            except Exception:
                error_code = 'Unknown'

            # Permissions and Authentication
            if error_code in ["AccessDenied", "InvalidAccessKeyId", "SignatureDoesNotMatch", "AllAccessDisabled"]:
                raise PermissionError(
                    "Authentication failed. Please verify your storage credentials, access keys, and permission policies."
                ) from e

            # Regional/Routing Errors
            elif error_code in ["PermanentRedirect", "AuthorizationHeaderMalformed"]:
                raise ValueError(
                    "The storage configuration is incorrect. Please contact your system administrator if the problem persists."
                ) from e

            # Throttling/Server Side
            elif error_code in ["SlowDown", "InternalError", "ServiceUnavailable"]:
                raise ConnectionError(
                    "The storage service is currently overloaded or experiencing temporary issues. Please wait a moment and try again."
                ) from e

            # Unhandled S3/botocore error
            raise RuntimeError("A technical issue occurred while setting up the storage agent. Please contact your system administrator if the problem persists.") from e
        finally:
            self.clear_secrets()
        
        # enable CORS the first time any agent is created
        # if not S3StorageAgent._cors_enabled:
        #     self._enable_cors()
        #     S3StorageAgent._cors_enabled = True

    def fetch_all_buckets(self) -> List[str]:
        resp = self.s3_client.list_buckets()
        # TODO: remove temporary solution to filter out the reserved buckets in the S3 managed by us:
        # bundle and inn-test
        if _bucket_access_level_enabled():  # true means enable dev access to all buckets;
            return [b['Name'] for b in resp.get('Buckets', [])]
        else: # false means hide reserved buckets
            return [b['Name'] for b in resp.get('Buckets', []) if b['Name'] not in ['bundle', 'inn-test']]

    def generate_access_links(
        self, resources: List[str], method: str, ttl: int
    ) -> Tuple[List[str], List[str]]:
        """Generate presigned URLs for many objects in one pass.

        Presigning is local HMAC work, so the cost of a batch is dominated by
        per-call overhead rather than the signing itself. Resolving the client
        method once and logging once, rather than per object, keeps a 10k-file
        manifest from emitting 10k log lines.
        """
        client_method = self._client_method_for(method)

        urls: List[str] = []
        for resource in resources:
            bucket, key = self._split_resource(resource)
            urls.append(self.s3_client.generate_presigned_url(
                ClientMethod=client_method,
                Params={"Bucket": bucket, "Key": key},
                ExpiresIn=ttl,
            ))

        logger.info(f"generate_access_links ({method}): {len(urls)} URL(s)")
        return urls, list(resources)

    @staticmethod
    def _client_method_for(method: str) -> str:
        client_method = {"write": "put_object", "read": "get_object"}.get(method)
        if client_method is None:
            raise ValueError(f"Unsupported access method {method!r}")
        return client_method

    @staticmethod
    def _split_resource(resource: str) -> Tuple[str, str]:
        try:
            bucket, key = resource.split("/", 1)
        except ValueError:
            raise ValueError(f"Bad S3 path: {resource!r}")
        return bucket, key

    def generate_access_link(
        self, resource: str, method: str, ttl: int
    ) -> Tuple[List[str], List[str]]:
        """Generate a presigned upload or download URL for an object."""
        client_method_by_access = {
            "write": "put_object",
            "read": "get_object",
        }
        client_method = client_method_by_access.get(method)
        if client_method is None:
            raise ValueError(f"Unsupported access method {method!r}")

        try:
            bucket, key = resource.split("/", 1)
        except ValueError:
            raise ValueError(f"Bad S3 path: {resource!r}")

        url = self.s3_client.generate_presigned_url(
            ClientMethod=client_method,
            Params={"Bucket": bucket, "Key": key},
            ExpiresIn=ttl
        )
        # Debug only because folder upload may generate thousands of URLs.
        logger.debug("generate_access_link (%s): URL for %s", method, resource)
        return [url], [resource]

    def delete_object(self, resource: str):
        """Delete an object identified by ``bucket/key``."""
        try:
            bucket, key = resource.split("/", 1)
        except ValueError:
            raise ValueError(f"Bad S3 path: {resource!r}")

        return self.s3_client.delete_object(Bucket=bucket, Key=key)

    def delete_objects(self, resources: List[str]):
        """Delete objects identified by ``bucket/key`` resource paths."""
        objects_by_bucket = {}
        for resource in resources:
            try:
                bucket, key = resource.split("/", 1)
            except ValueError:
                raise ValueError(f"Bad S3 path: {resource!r}")
            objects_by_bucket.setdefault(bucket, []).append({"Key": key})

        for bucket, objects in objects_by_bucket.items():
            for i in range(0, len(objects), 1000):
                self.s3_client.delete_objects(
                    Bucket=bucket,
                    Delete={"Objects": objects[i:i + 1000], "Quiet": True},
                )

    def get_object_metadata(self, resource: str):
        """Return metadata for an object identified by ``bucket/key``."""
        try:
            bucket, key = resource.split("/", 1)
        except ValueError:
            raise ValueError(f"Bad S3 path: {resource!r}")

        return self.s3_client.head_object(Bucket=bucket, Key=key)

    def _enable_cors(self):
        """
        Permissive CORS for local dev: allow all origins,
        all typical S3 methods, and OPTIONS preflights.
        """
        cors_conf = {
            "CORSRules": [{
                "AllowedOrigins": ["*"],  # dev only!
                "AllowedMethods": [  # include OPTIONS + HEAD
                    "GET", "PUT", "POST", "DELETE", "HEAD"
                ],
                "AllowedHeaders": ["*"],
                "ExposeHeaders": ["ETag"],
                "MaxAgeSeconds": 300
            }]
        }
        for bucket in self.fetch_all_buckets():
            logger.info(f"Applying dev CORS to bucket {bucket}")
            self.s3_client.put_bucket_cors(
                Bucket=bucket,
                CORSConfiguration=cors_conf
            )

    def config(self, secrets: bool = False) -> dict:
        config = super().config(secrets)
        if self.region_name:
            config["region_name"] = self.region_name
        return config

    @classmethod
    def secrets(cls) -> set[str]:
        return {"aws_secret_access_key"}

    def close(self):
        if hasattr(self, "s3_client"):
            self.s3_client.close()

    def __str__(self):
        return f"S3StorageAgent(instance_url={self.instance_url})"
