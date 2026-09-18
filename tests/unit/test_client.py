import json
from collections import deque
from urllib.parse import parse_qs, urlsplit

import pytest
import requests

import api.disk_client as client_module
from api.disk_client import API_URL, DiskClient, DiskClientError
from tests.conftest import isolated_root

pytestmark = pytest.mark.unit

NOT_FOUND = {"error": "not-found", "message": "Missing", "description": "Missing"}
OPERATION_URL = API_URL + "/operations/unit-operation"


@pytest.fixture
def http(monkeypatch):
    replies = deque()
    calls = []
    clock = [0.0]

    def send(session, request, **kwargs):
        calls.append((request, kwargs))
        assert replies, "Unexpected HTTP call in an offline test"
        reply = replies.popleft()
        if isinstance(reply, Exception):
            raise reply
        code, body, headers = reply
        response = requests.Response()
        response.status_code = code
        response._content = body if isinstance(body, bytes) else json.dumps(body).encode()
        response.headers.update({"Content-Type": "application/json", **headers})
        response.request = request
        response.url = request.url
        return response

    def advance(seconds):
        clock[0] += seconds

    monkeypatch.setattr(requests.Session, "send", send)
    monkeypatch.setattr(client_module, "monotonic", lambda: clock[0])
    monkeypatch.setattr(client_module, "sleep", advance)
    yield replies, calls, clock
    assert not replies, "An expected HTTP call was not made"


@pytest.fixture
def client(http):
    instance = DiskClient("offline-placeholder", operation_timeout=3, poll_interval=1)
    yield instance
    instance.close()


def test_query_encoding_and_request_timeouts(client, http):
    replies, calls, _ = http
    replies.append((201, {}, {}))
    source = "disk:/Папка с пробелами/#&+%=.txt"
    destination = "disk:/другая папка/file.txt"

    client.copy_resource(source, destination, overwrite=True)

    request, options = calls[0]
    assert parse_qs(urlsplit(request.url).query) == {
        "from": [source],
        "path": [destination],
        "overwrite": ["true"],
        "force_async": ["false"],
    }
    assert request.headers["Authorization"] == "OAuth offline-placeholder"
    assert options["timeout"] == (5.0, 30.0)
    assert options["allow_redirects"] is False


def test_storage_transfer_never_receives_oauth(client, http):
    replies, calls, _ = http
    replies.extend(
        [
            (201, b"", {}),
            (302, b"", {"Location": "https://example.test/storage"}),
            (200, b"file bytes", {}),
        ]
    )

    client.upload("https://example.test/upload", b"file bytes")
    response = client.download("https://example.test/download")

    assert response.content == b"file bytes"
    assert calls[0][0].body == b"file bytes"
    assert all("Authorization" not in request.headers for request, _ in calls)
    assert client.session.trust_env is False
    assert client.transfer_session.trust_env is False


def test_operation_link_cannot_exfiltrate_oauth(client, http):
    with pytest.raises(DiskClientError, match="non-operation URL"):
        client.wait_operation("https://example.test/v1/disk/operations/leak")
    assert http[1] == []


def test_operation_polling_waits_for_terminal_success(client, http):
    replies, calls, clock = http
    replies.extend([(200, {"status": "in-progress"}, {}), (200, {"status": "success"}, {})])

    client.wait_operation(OPERATION_URL)

    assert len(calls) == 2
    assert clock[0] == 1


def test_failed_operation_is_reported_without_retry(client, http):
    http[0].append((200, {"status": "failed"}, {}))

    with pytest.raises(DiskClientError, match="operation failed"):
        client.wait_operation(OPERATION_URL)
    assert len(http[1]) == 1


def test_operation_polling_has_a_deadline(client, http):
    http[0].extend([(200, {"status": "in-progress"}, {})] * 3)

    with pytest.raises(DiskClientError, match="Timed out"):
        client.wait_operation(OPERATION_URL)
    assert http[2][0] == 3


def test_overwrite_polling_rejects_old_metadata(client, http):
    expected = {"size": 12, "md5": "new-checksum"}
    http[0].extend(
        [
            (404, NOT_FOUND, {}),
            (200, {"size": 5, "md5": "old-checksum"}, {}),
            (200, expected, {}),
        ]
    )

    response = client.wait_resource("disk:/unit/file", expected=expected)

    assert response.json() == expected
    assert len(http[1]) == 3


def test_resource_polling_does_not_hide_authorization_failure(client, http):
    http[0].append((401, {}, {}))

    with pytest.raises(DiskClientError, match="HTTP 401"):
        client.wait_resource("disk:/unit/file")
    assert len(http[1]) == 1


def test_absence_polling_waits_until_resource_disappears(client, http):
    path = "disk:/unit/source.txt"
    http[0].extend([(200, {"path": path}, {}), (404, NOT_FOUND, {})])

    response = client.wait_resource(path, absent=True)

    assert response.status_code == 404
    assert len(http[1]) == 2
    assert http[2][0] == 1


def test_absence_polling_reports_resource_still_present(client, http):
    path = "disk:/unit/source.txt"
    http[0].extend([(200, {"path": path}, {})] * 3)

    with pytest.raises(DiskClientError, match="Timed out") as error:
        client.wait_resource(path, absent=True)

    assert "absence" in str(error.value)
    assert path in str(error.value)
    assert "last HTTP 200" in str(error.value)
    assert http[2][0] == 3


def test_transport_error_does_not_expose_signed_url(client, http):
    http[0].append(requests.Timeout("https://example.test/?signature=private-value"))

    with pytest.raises(DiskClientError) as error:
        client.upload("https://example.test/upload", b"payload")

    assert str(error.value) == "PUT request failed (Timeout)"
    assert error.value.__suppress_context__ is True


def test_cleanup_runs_if_setup_fails(client, http):
    http[0].extend(
        [
            (201, {"href": API_URL + "/resources", "method": "GET", "templated": False}, {}),
            (500, {}, {}),
            (204, b"", {}),
            (404, NOT_FOUND, {}),
        ]
    )

    with pytest.raises(DiskClientError, match="HTTP 500"), isolated_root(client):
        pytest.fail("Setup should have failed before yield")

    calls = http[1]
    assert [request.method for request, _ in calls] == ["PUT", "GET", "DELETE", "GET"]
    paths = [parse_qs(urlsplit(request.url).query)["path"][0] for request, _ in calls]
    assert len(set(paths)) == 1
    assert paths[0].startswith("disk:/qa-api-")
    assert parse_qs(urlsplit(calls[2][0].url).query)["permanently"] == ["true"]


def test_cleanup_after_test_failure_waits_for_async_delete(client, http, monkeypatch):
    monkeypatch.setattr("tests.conftest.assert_resource", lambda *args: None)
    http[0].extend(
        [
            (201, {"href": API_URL + "/resources", "method": "GET", "templated": False}, {}),
            (200, {}, {}),
            (202, {"href": OPERATION_URL, "method": "GET", "templated": False}, {}),
            (200, {"status": "success"}, {}),
            (404, NOT_FOUND, {}),
        ]
    )

    with pytest.raises(AssertionError, match="simulated test failure"), isolated_root(client):
        raise AssertionError("simulated test failure")

    assert [request.method for request, _ in http[1]] == ["PUT", "GET", "DELETE", "GET", "GET"]


def test_cleanup_accepts_already_deleted_root(client, http, monkeypatch):
    monkeypatch.setattr("tests.conftest.assert_resource", lambda *args: None)
    http[0].extend(
        [
            (201, {"href": API_URL + "/resources", "method": "GET", "templated": False}, {}),
            (200, {}, {}),
            (404, NOT_FOUND, {}),
            (404, NOT_FOUND, {}),
        ]
    )

    with isolated_root(client):
        pass
