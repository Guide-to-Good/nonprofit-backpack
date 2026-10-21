"""A Storage adapter for S3-compatible object storage. The library hashes the bytes; this decides where they live
and how `access` is enforced. Here: private objects by default, a public-read ACL for `public`.

    pip install boto3
    create_backpack(intake, storage=S3Storage("my-bucket"))
"""
from __future__ import annotations

import boto3


class S3Storage:
    def __init__(self, bucket: str, prefix: str = "backpacks/"):
        self.bucket, self.prefix, self.s3 = bucket, prefix, boto3.client("s3")

    def put(self, data: bytes, filename: str, access: str) -> str:
        key = f"{self.prefix}{filename}"
        self.s3.put_object(Bucket=self.bucket, Key=key, Body=data, ACL="public-read" if access == "public" else "private")
        return f"s3://{self.bucket}/{key}"          # or a presigned/CDN URL, your call

    def collect(self) -> dict[str, bytes]:
        return {}                                   # nothing travels inside the zip
