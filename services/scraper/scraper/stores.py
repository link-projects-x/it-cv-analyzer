"""Storage backends for raw vacancy HTML: S3 in Lambda, a local directory for development."""

from __future__ import annotations

import json
from pathlib import Path


class S3RawStore:
    def __init__(self, bucket: str, s3_client=None):
        if s3_client is None:
            import boto3  # available in the Lambda Python runtime

            s3_client = boto3.client("s3")
        self._s3 = s3_client
        self._bucket = bucket

    def exists(self, key: str) -> bool:
        from botocore.exceptions import ClientError

        try:
            self._s3.head_object(Bucket=self._bucket, Key=key)
            return True
        except ClientError as exc:
            if exc.response["Error"]["Code"] in ("404", "NoSuchKey", "NotFound"):
                return False
            raise

    def put_html(self, key: str, body: bytes, metadata: dict[str, str]) -> None:
        self._s3.put_object(
            Bucket=self._bucket,
            Key=key,
            Body=body,
            ContentType="text/html; charset=utf-8",
            Metadata=metadata,
        )


class LocalRawStore:
    """Writes <root>/raw/dou-<id>.html plus a .meta.json sidecar with the same metadata S3 would hold."""

    def __init__(self, root: Path):
        self._root = root

    def exists(self, key: str) -> bool:
        return (self._root / key).exists()

    def put_html(self, key: str, body: bytes, metadata: dict[str, str]) -> None:
        path = self._root / key
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(body)
        path.with_suffix(".meta.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
