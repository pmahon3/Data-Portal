import re
import logging
import boto3
import treelib
from pathlib import Path
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError

from typing import List, Tuple
from core.connectivity import AbstractStorageAgent

logger = logging.getLogger('storage.s3')


class S3StorageAgent(AbstractStorageAgent):
    FLAVOUR = 's3'
    CONFIG = {
        "aws_access_key_id": str,
        "aws_secret_access_key": str
    }

    # ensure CORS only applies once
    _cors_enabled = False

    def __init__(self,
                 instance_url: str,
                 aws_access_key_id: str,
                 aws_secret_access_key: str):
        super().__init__(instance_url)

        self.s3_client = boto3.client(
            's3',
            endpoint_url=instance_url,
            aws_access_key_id=aws_access_key_id,
            aws_secret_access_key=aws_secret_access_key,
            config=Config(signature_version="s3v4")
        )


        try:
            # boto3 is lazy and doesn't throw an error until the client is actually used
            self.s3_client.list_buckets()

        except ClientError as e:
            error_code = e.response.get('Error', {}).get('Code', 'Unknown')
            if error_code == 'AccessDenied':
                raise PermissionError("S3 Access Denied") from e
            raise ValueError(f"S3 Client Error [{error_code}]") from e
        
        except BotoCoreError as e:
            # Handles DNS, Timeouts, and Connection Refused
            raise ConnectionError("S3 Connection failed") from e
            
        except Exception as e:
            raise RuntimeError("Unexpected S3 error") from e
        
        # Attempt to build the in-memory file tree
        self.file_tree = treelib.Tree()
        self._load_file_tree()
        
        # enable CORS the first time any agent is created
        # if not S3StorageAgent._cors_enabled:
        #     self._enable_cors()
        #     S3StorageAgent._cors_enabled = True

    def _load_file_tree(self):
        self.file_tree.create_node('root', 'root')
        for bucket in self.fetch_all_buckets():
            self._add_file_to_tree(bucket)
            for obj in self.fetch_all_bucket_keys(bucket):
                # Use forward slash for S3 paths
                self._add_file_to_tree((Path(bucket) / obj).as_posix())

    def fetch_all_buckets(self) -> List[str]:
        resp = self.s3_client.list_buckets()
        return [b['Name'] for b in resp.get('Buckets', [])]

    def fetch_all_bucket_keys(self, bucket: str) -> List[str]:
        resp = self.s3_client.list_objects_v2(Bucket=bucket)
        return [o['Key'] for o in resp.get('Contents', [])]

    def generate_access_link(
        self, resource: str, method: str, ttl: int
    ) -> Tuple[List[str], List[str]]:
        # map to boto3 operation
        if method == "read":
            verb = "get_object"
        elif method == "write":
            verb = "put_object"
        elif method == "delete":
            verb = "delete_object"
        else:
            raise ValueError(f"Unsupported method {method!r}")

        # WRITE/DELETE: single presigned URL for exact resource
        if verb in ("put_object", "delete_object"):
            try:
                bucket, key = resource.split("/", 1)
            except ValueError:
                raise ValueError(f"Bad S3 path: {resource!r}")
            url = self.s3_client.generate_presigned_url(
                ClientMethod=verb,
                Params={"Bucket": bucket, "Key": key},
                ExpiresIn=ttl
            )
            logger.info(f"generate_access_link ({method}): URL for {resource}")
            return [url], [resource]

        # READ: treat resource as regex, full‐match
        # Normalize backslashes to forward slashes for portability
        resource = Path(resource).as_posix()
        pattern = re.compile(resource)
        all_paths = [
            n.identifier
            for n in self.file_tree.all_nodes()
            if n.identifier != 'root'
        ]
        matched = [p for p in all_paths if pattern.fullmatch(p)]
        if not matched:
            logger.info(f"No objects match regex: {resource}")
            return [], []

        urls = []
        for path in matched:
            bucket, key = path.split("/", 1)
            urls.append(self.s3_client.generate_presigned_url(
                ClientMethod=verb,
                Params={"Bucket": bucket, "Key": key},
                ExpiresIn=ttl
            ))

        logger.info(f"generate_access_link (read): matched {len(matched)} for {resource}")
        return urls, matched

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
        return super().config(secrets)

    def _secrets(self):
        creds = self.s3_client._request_signer._credentials
        return {
            "aws_access_key_id": creds.access_key,
            "aws_secret_access_key": creds.secret_key
        }

    def refresh_connection(self):
        creds = self.s3_client._request_signer._credentials
        self.s3_client = boto3.client(
            's3',
            instance_url=self.instance_url,
            aws_access_key_id=creds.access_key,
            aws_secret_access_key=creds.secret_key
        )

    def close(self):
        self.s3_client.close()

    def smart_refresh_file_tree(self):
        """
        Efficiently refresh the S3 file tree using differential updates.

        Compares current S3 state with cached tree and handles both additions and deletions.
        This is much faster than rebuilding the entire tree for large buckets.
        """
        logger.info("Starting smart refresh of S3 file tree")

        # Get current files from S3
        current_files = set()
        for bucket in self.fetch_all_buckets():
            current_files.add(bucket)
            for obj in self.fetch_all_bucket_keys(bucket):
                # Use forward slash for S3 paths
                current_files.add((Path(bucket) / obj).as_posix())

        # Get cached files from tree
        cached_files = set(
            n.identifier
            for n in self.file_tree.all_nodes()
            if n.identifier != 'root'
        )

        # Find new files (additions)
        new_files = current_files - cached_files

        # Find deleted files (removals)
        deleted_files = cached_files - current_files

        # Add new files to tree
        for file_path in new_files:
            self._add_file_to_tree(file_path)
            logger.debug(f"Added new file to tree: {file_path}")

        # Remove deleted files from tree
        for file_path in deleted_files:
            self._remove_file_from_tree(file_path)
            logger.debug(f"Removed deleted file from tree: {file_path}")

        # Log summary
        changes = []
        if new_files:
            changes.append(f"added {len(new_files)}")
        if deleted_files:
            changes.append(f"removed {len(deleted_files)}")

        if changes:
            logger.info(f"Smart refresh complete: {', '.join(changes)} files")
        else:
            logger.info("Smart refresh complete: no changes")

    def __str__(self):
        return f"S3StorageAgent(instance_url={self.instance_url})"
    