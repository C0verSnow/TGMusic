import json
import uuid

import boto3
import requests
from botocore.config import Config as S3Config
from botocore.exceptions import BotoCoreError, ClientError

from models import StorageError


class D1:
    def __init__(self, config, session=None):
        self.session = session or requests.Session()
        self.url = (f"https://api.cloudflare.com/client/v4/accounts/{config.cloudflare_account_id}"
                    f"/d1/database/{config.cloudflare_d1_database_id}/query")
        self.headers = {"Authorization": f"Bearer {config.cloudflare_api_token}"}

    def query(self, sql, params=()):
        try:
            response = self.session.post(self.url, headers=self.headers,
                                         json={"sql": sql, "params": list(params)}, timeout=40)
            response.raise_for_status()
            data = response.json()
            if not data.get("success") or any(not row.get("success") for row in data["result"]):
                raise StorageError("D1 query failed")
            return data["result"][0].get("results", [])
        except (requests.RequestException, ValueError, KeyError):
            raise StorageError("D1 unavailable; sync stopped") from None


class R2:
    def __init__(self, config, proxy_url=None):
        self.bucket = config.r2_bucket
        self.client = boto3.client(
            "s3", endpoint_url=config.r2_endpoint, region_name="auto",
            aws_access_key_id=config.r2_access_key_id,
            aws_secret_access_key=config.r2_secret_access_key,
            config=S3Config(signature_version="s3v4", retries={"max_attempts": 2},
                            connect_timeout=15, read_timeout=60,
                            proxies={"https": proxy_url} if proxy_url else None))

    def get(self, key, optional=False):
        try:
            obj = self.client.get_object(Bucket=self.bucket, Key=key)
            return obj["Body"].read(), obj["ETag"], obj.get("Metadata", {})
        except ClientError as error:
            if optional and error.response["Error"]["Code"] in {"NoSuchKey", "404"}:
                return None
            raise StorageError("R2 read failed; existing data preserved") from None
        except BotoCoreError:
            raise StorageError("R2 unavailable") from None

    def put(self, key, data, etag=None, create=False, metadata=None):
        args = dict(Bucket=self.bucket, Key=key, Body=data, Metadata=metadata or {})
        if etag:
            args["IfMatch"] = etag
        if create:
            args["IfNoneMatch"] = "*"
        try:
            return self.client.put_object(**args)["ETag"]
        except (ClientError, BotoCoreError):
            raise StorageError("R2 write failed or version conflict; previous data preserved") from None

    def versioned_put(self, key, data, etag, metadata):
        self.put(f"{key}.versions/{uuid.uuid4().hex}", data, create=True, metadata=metadata)
        return self.put(key, data, etag=etag, create=etag is None, metadata=metadata)

    def verify_installation(self, installation_id):
        obj = self.get("sync/installation.json")
        try:
            valid = json.loads(obj[0])["installation_id"] == installation_id
        except (ValueError, KeyError):
            valid = False
        if not valid:
            raise StorageError("R2/D1 installation mismatch; restore state before running")
