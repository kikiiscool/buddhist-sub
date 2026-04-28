import os
import tempfile

import boto3
from botocore.client import Config

from worker.config import get_settings

_settings = get_settings()


def s3():
    return boto3.client(
        "s3",
        endpoint_url=_settings.s3_endpoint,
        aws_access_key_id=_settings.s3_access_key,
        aws_secret_access_key=_settings.s3_secret_key,
        region_name=_settings.s3_region,
        config=Config(signature_version="s3v4"),
    )


def download_to_tmp(key: str, suffix: str = "") -> str:
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    tmp.close()
    s3().download_file(_settings.s3_bucket, key, tmp.name)
    return tmp.name


def upload_file(local_path: str, key: str, content_type: str = "application/octet-stream") -> str:
    s3().upload_file(
        local_path,
        _settings.s3_bucket,
        key,
        ExtraArgs={"ContentType": content_type},
    )
    return key
