from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from uuid import uuid4

import pytest
from dotenv import load_dotenv

from api.disk_client import DiskClient
from tests.helpers import assert_error, assert_resource, finish_mutation

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--run-unauthenticated",
        action="store_true",
        help="Run the two read-only missing/invalid token scenarios without a configured token",
    )


@pytest.fixture(scope="session")
def configured_token() -> str | None:
    import os

    load_dotenv(PROJECT_ROOT / ".env", override=False)
    token = os.getenv("YANDEX_DISK_TOKEN", "").strip()
    return token if token and token != "your_token_here" else None


@pytest.fixture
def api_client(configured_token: str | None) -> Iterator[DiskClient]:
    if not configured_token:
        pytest.skip("Set YANDEX_DISK_TOKEN for a separate test account in the environment or .env")
    client = DiskClient(configured_token)
    try:
        yield client
    finally:
        client.close()


@pytest.fixture
def unauthorized_client(
    request: pytest.FixtureRequest, configured_token: str | None
) -> Iterator[DiskClient]:
    if not configured_token and not request.config.getoption("--run-unauthenticated"):
        pytest.skip("No token configured; use --run-unauthenticated for read-only auth checks")
    token = None if request.param == "missing" else f"invalid-{uuid4().hex}"
    client = DiskClient(token)
    try:
        yield client
    finally:
        client.close()


@contextmanager
def isolated_root(client: DiskClient) -> Iterator[str]:
    root = f"disk:/qa-api-{uuid4().hex}"
    try:
        finish_mutation(client, client.create_folder(root), 201)
        assert_resource(client.wait_resource(root).json(), root, "dir")
        yield root
    finally:
        response = client.delete_resource(root)
        if response.status_code != 404:
            finish_mutation(client, response, 204, 202)
        else:
            assert_error(response, 404)
        assert_error(client.wait_resource(root, absent=True), 404)


@pytest.fixture
def resource_root(api_client: DiskClient) -> Iterator[str]:
    with isolated_root(api_client) as root:
        yield root
