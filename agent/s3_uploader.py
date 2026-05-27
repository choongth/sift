import asyncio
import os
from pathlib import Path

import boto3


def _upload_and_sign(local_path: str, bucket: str, s3_key: str, expiry: int) -> str:
    """Blocking: upload file to S3, return a presigned GET URL."""
    client = boto3.client("s3")
    client.upload_file(
        local_path,
        bucket,
        s3_key,
        ExtraArgs={"ContentType": "text/markdown; charset=utf-8"},
    )
    return client.generate_presigned_url(
        "get_object",
        Params={
            "Bucket": bucket,
            "Key": s3_key,
            "ResponseContentDisposition": f'attachment; filename="{Path(s3_key).name}"',
        },
        ExpiresIn=expiry,
    )


async def upload_report(local_path: str) -> str:
    """Upload a report file to S3 and return a presigned download URL.

    Raises ValueError if S3_BUCKET_NAME is unset.
    Raises ClientError / BotoCoreError on AWS failures.
    """
    bucket = os.environ.get("S3_BUCKET_NAME", "")
    if not bucket:
        raise ValueError("S3_BUCKET_NAME environment variable is not set")
    expiry = int(os.environ.get("S3_PRESIGNED_EXPIRY", "3600"))
    s3_key = f"reports/{Path(local_path).name}"
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _upload_and_sign, local_path, bucket, s3_key, expiry)
