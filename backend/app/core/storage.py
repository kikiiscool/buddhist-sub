import boto3
from botocore.client import Config

from app.core.config import get_settings

settings = get_settings()


def s3_client():
    return boto3.client(
        "s3",
        endpoint_url=settings.s3_endpoint,
        aws_access_key_id=settings.s3_access_key,
        aws_secret_access_key=settings.s3_secret_key,
        region_name=settings.s3_region,
        config=Config(signature_version="s3v4"),
    )


def presigned_put(key: str, content_type: str = "audio/mpeg", expires: int = 3600) -> str:
    return s3_client().generate_presigned_url(
        "put_object",
        Params={"Bucket": settings.s3_bucket, "Key": key, "ContentType": content_type},
        ExpiresIn=expires,
    )


def presigned_get(key: str, expires: int = 3600) -> str:
    return s3_client().generate_presigned_url(
        "get_object",
        Params={"Bucket": settings.s3_bucket, "Key": key},
        ExpiresIn=expires,
    )
