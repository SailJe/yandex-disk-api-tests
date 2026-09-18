import hashlib
from datetime import datetime
from os.path import splitext
from typing import Any
from urllib.parse import urlsplit
from uuid import uuid4

import requests

from api.disk_client import DiskClient


def unique_path(parent: str, name: str = "resource") -> str:
    stem, suffix = splitext(name)
    return f"{parent}/{stem}-{uuid4().hex}{suffix}"


def assert_status(response: requests.Response, *expected: int) -> None:
    assert response.status_code in expected, (
        f"Expected HTTP {expected}, got HTTP {response.status_code}"
    )


def assert_error(response: requests.Response, status: int) -> None:
    assert_status(response, status)
    assert response.headers.get("Content-Type", "").split(";")[0] == "application/json"
    body = response.json()
    for field in ("error", "message", "description"):
        assert isinstance(body[field], str) and body[field]


def assert_link(response: requests.Response, method: str = "GET") -> str:
    body = response.json()
    assert body["method"] == method
    assert body["templated"] is False
    href = body["href"]
    assert isinstance(href, str)
    assert urlsplit(href).scheme == "https"
    assert urlsplit(href).hostname
    return href


def finish_mutation(client: DiskClient, response: requests.Response, *expected: int) -> None:
    assert_status(response, *expected)
    if response.status_code == 202:
        client.wait_operation(assert_link(response))
    elif response.status_code == 201:
        assert_link(response)
    elif response.status_code == 204:
        assert response.content == b""


def assert_resource(metadata: dict[str, Any], path: str, kind: str) -> None:
    assert metadata["path"] == path
    assert metadata["name"] == path.rsplit("/", 1)[1]
    assert metadata["type"] == kind
    for field in ("created", "modified"):
        assert isinstance(metadata[field], str)
        assert datetime.fromisoformat(metadata[field]).tzinfo is not None


def file_identity(content: bytes) -> dict[str, Any]:
    return {"size": len(content), "md5": hashlib.md5(content, usedforsecurity=False).hexdigest()}


def assert_file(metadata: dict[str, Any], path: str, content: bytes) -> None:
    assert_resource(metadata, path, "file")
    for field, value in file_identity(content).items():
        assert metadata[field] == value
    assert isinstance(metadata["mime_type"], str) and "/" in metadata["mime_type"]


def get_metadata(client: DiskClient, path: str) -> dict[str, Any]:
    response = client.get_resource(path)
    assert_status(response, 200)
    return response.json()


def put_file(client: DiskClient, path: str, content: bytes, *, overwrite: bool = False) -> dict:
    link = client.get_upload_link(path, overwrite=overwrite)
    assert_status(link, 200)
    response = client.upload(assert_link(link, "PUT"), content)
    assert_status(response, 201, 202)
    metadata = client.wait_resource(path, expected=file_identity(content)).json()
    assert_file(metadata, path, content)
    return metadata


def read_file(client: DiskClient, path: str) -> bytes:
    link = client.get_download_link(path)
    assert_status(link, 200)
    response = client.download(assert_link(link))
    assert_status(response, 200)
    return response.content


def snapshot(client: DiskClient, path: str) -> dict[str, Any]:
    data = get_metadata(client, path)
    fields = ("name", "path", "type", "size", "md5", "created", "modified", "mime_type")
    return {field: data[field] for field in fields}
