"""S3 layout used by the matcher and the HTTP API, with an S3 and a local implementation.

Existence checks go through ListObjectsV2 with the key as prefix: GetObject and HeadObject on a missing key answer
403 instead of 404 unless the role may list the bucket, and the IAM policy grants ListBucket per prefix.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Protocol


class Store(Protocol):
    def exists(self, key: str) -> bool: ...
    def get_json(self, key: str) -> dict | None: ...
    def get_text(self, key: str) -> str | None: ...
    def put_json(self, key: str, doc: dict) -> None: ...
    def count(self, prefix: str) -> int: ...


class S3Store:
    def __init__(self, bucket: str, s3_client=None, region: str | None = None):
        if s3_client is None:
            import boto3
            from botocore.config import Config

            # Regional virtual-hosted URLs and SigV4, so a presigned POST works outside us-east-1 as well
            s3_client = boto3.client(
                "s3", region_name=region, config=Config(signature_version="s3v4", s3={"addressing_style": "virtual"})
            )
        self._s3 = s3_client
        self._bucket = bucket

    def exists(self, key: str) -> bool:
        page = self._s3.list_objects_v2(Bucket=self._bucket, Prefix=key, MaxKeys=1)
        return any(obj["Key"] == key for obj in page.get("Contents", []))

    def get_text(self, key: str) -> str | None:
        if not self.exists(key):
            return None
        return self._s3.get_object(Bucket=self._bucket, Key=key)["Body"].read().decode("utf-8")

    def get_json(self, key: str) -> dict | None:
        text = self.get_text(key)
        return None if text is None else json.loads(text)

    def put_json(self, key: str, doc: dict) -> None:
        self._s3.put_object(
            Bucket=self._bucket,
            Key=key,
            Body=json.dumps(doc, ensure_ascii=False, indent=2).encode("utf-8"),
            ContentType="application/json; charset=utf-8",
        )

    def count(self, prefix: str) -> int:
        """Number of objects under prefix (used for the daily upload quota)."""
        total, token = 0, None
        while True:
            kwargs = {"Bucket": self._bucket, "Prefix": prefix}
            if token:
                kwargs["ContinuationToken"] = token
            page = self._s3.list_objects_v2(**kwargs)
            total += page.get("KeyCount", 0)
            if not page.get("IsTruncated"):
                return total
            token = page["NextContinuationToken"]

    def presigned_post(self, key: str, content_type: str, max_bytes: int, expires_in: int) -> dict:
        """POST policy for exactly this key and content type, 1..max_bytes bytes, valid expires_in seconds."""
        return self._s3.generate_presigned_post(
            Bucket=self._bucket,
            Key=key,
            Fields={"Content-Type": content_type},
            Conditions=[{"Content-Type": content_type}, ["content-length-range", 1, max_bytes]],
            ExpiresIn=expires_in,
        )


class LocalStore:
    """Mirrors the S3 layout under a local directory."""

    def __init__(self, root: Path):
        self._root = root

    def exists(self, key: str) -> bool:
        return (self._root / key).is_file()

    def get_text(self, key: str) -> str | None:
        path = self._root / key
        return path.read_text(encoding="utf-8") if path.is_file() else None

    def get_json(self, key: str) -> dict | None:
        text = self.get_text(key)
        return None if text is None else json.loads(text)

    def put_json(self, key: str, doc: dict) -> None:
        path = self._root / key
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")

    def count(self, prefix: str) -> int:
        base = self._root / prefix
        return sum(1 for p in base.rglob("*") if p.is_file()) if base.is_dir() else 0
