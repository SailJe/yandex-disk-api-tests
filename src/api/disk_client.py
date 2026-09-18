from collections.abc import Mapping
from time import monotonic, sleep
from typing import Any
from urllib.parse import urlsplit

import requests

API_URL = "https://cloud-api.yandex.net/v1/disk"


class DiskClientError(RuntimeError):
    pass


class DiskClient:
    def __init__(
        self,
        token: str | None = None,
        *,
        timeout: tuple[float, float] = (5.0, 30.0),
        operation_timeout: float = 90.0,
        poll_interval: float = 1.0,
    ) -> None:
        if min(*timeout, operation_timeout, poll_interval) <= 0:
            raise ValueError("Timeouts and polling interval must be positive")
        self.timeout = timeout
        self.operation_timeout = operation_timeout
        self.poll_interval = poll_interval
        self.session = requests.Session()
        self.session.headers.update(
            {"Accept": "application/json", "Content-Type": "application/json"}
        )
        self.session.trust_env = False
        if token:
            self.session.headers["Authorization"] = f"OAuth {token}"
        self.transfer_session = requests.Session()
        self.transfer_session.trust_env = False

    def close(self) -> None:
        self.session.close()
        self.transfer_session.close()

    def _send(
        self,
        session: requests.Session,
        method: str,
        url: str,
        *,
        timeout: tuple[float, float] | None = None,
        **kwargs: Any,
    ) -> requests.Response:
        try:
            return session.request(
                method, url, timeout=timeout or self.timeout, allow_redirects=False, **kwargs
            )
        except requests.RequestException as exc:
            raise DiskClientError(f"{method} request failed ({type(exc).__name__})") from None

    def _request(self, method: str, endpoint: str, **params: Any) -> requests.Response:
        query = {
            key: str(value).lower() if isinstance(value, bool) else value
            for key, value in params.items()
            if value is not None
        }
        return self._send(self.session, method, API_URL + endpoint, params=query)

    def get_resource(self, path: str, **params: Any) -> requests.Response:
        return self._request("GET", "/resources", path=path, **params)

    def create_folder(self, path: str | None) -> requests.Response:
        return self._request("PUT", "/resources", path=path)

    def delete_resource(self, path: str, *, force_async: bool = False) -> requests.Response:
        return self._request(
            "DELETE", "/resources", path=path, permanently=True, force_async=force_async
        )

    def copy_resource(
        self, source: str, destination: str, *, overwrite: bool = False, force_async: bool = False
    ) -> requests.Response:
        return self._request(
            "POST",
            "/resources/copy",
            **{"from": source, "path": destination},
            overwrite=overwrite,
            force_async=force_async,
        )

    def move_resource(
        self, source: str, destination: str, *, overwrite: bool = False, force_async: bool = False
    ) -> requests.Response:
        return self._request(
            "POST",
            "/resources/move",
            **{"from": source, "path": destination},
            overwrite=overwrite,
            force_async=force_async,
        )

    def get_upload_link(self, path: str, *, overwrite: bool = False) -> requests.Response:
        return self._request("GET", "/resources/upload", path=path, overwrite=overwrite)

    def get_download_link(self, path: str) -> requests.Response:
        return self._request("GET", "/resources/download", path=path)

    @staticmethod
    def _validate_url(url: str, *, operation: bool = False) -> None:
        parsed = urlsplit(url)
        if (
            parsed.scheme != "https"
            or not parsed.hostname
            or parsed.username
            or parsed.password
            or parsed.fragment
        ):
            raise DiskClientError("API returned an invalid HTTPS URL")
        if operation and (
            parsed.hostname != "cloud-api.yandex.net"
            or parsed.port not in (None, 443)
            or not (
                parsed.path == "/v1/disk/operations"
                or parsed.path.startswith("/v1/disk/operations/")
            )
        ):
            raise DiskClientError("Refusing to send OAuth to a non-operation URL")

    def upload(self, href: str, content: bytes) -> requests.Response:
        self._validate_url(href)
        return self._send(
            self.transfer_session,
            "PUT",
            href,
            data=content,
            headers={"Content-Type": "application/octet-stream"},
        )

    def download(self, href: str) -> requests.Response:
        for _ in range(5):
            self._validate_url(href)
            response = self._send(self.transfer_session, "GET", href)
            if response.status_code != 302:
                return response
            href = response.headers.get("Location", "")
        raise DiskClientError("Too many storage redirects")

    @staticmethod
    def _json(response: requests.Response) -> dict[str, Any]:
        try:
            data = response.json()
        except ValueError:
            raise DiskClientError("Expected a JSON object from the API") from None
        if not isinstance(data, dict):
            raise DiskClientError("Expected a JSON object from the API")
        return data

    def _poll_timeout(self, deadline: float, context: str = "the API state") -> tuple[float, float]:
        remaining = deadline - monotonic()
        if remaining <= 0:
            raise DiskClientError(f"Timed out waiting for {context}")
        return min(self.timeout[0], remaining), min(self.timeout[1], remaining)

    def _pause(self, deadline: float, context: str = "the API state") -> None:
        remaining = deadline - monotonic()
        if remaining <= 0:
            raise DiskClientError(f"Timed out waiting for {context}")
        sleep(min(self.poll_interval, remaining))

    def wait_operation(self, href: str) -> None:
        self._validate_url(href, operation=True)
        deadline = monotonic() + self.operation_timeout
        while True:
            response = self._send(self.session, "GET", href, timeout=self._poll_timeout(deadline))
            if response.status_code != 200:
                raise DiskClientError(f"Operation status returned HTTP {response.status_code}")
            status = self._json(response).get("status")
            if status == "success":
                return
            if status == "failed":
                raise DiskClientError("Asynchronous operation failed")
            if status != "in-progress":
                raise DiskClientError("Unknown operation status")
            self._pause(deadline)

    def wait_resource(
        self, path: str, *, expected: Mapping[str, Any] | None = None, absent: bool = False
    ) -> requests.Response:
        deadline = monotonic() + self.operation_timeout
        target = f"{'absence' if absent else 'matching metadata'} at {path!r}"
        context = target
        while True:
            response = self._send(
                self.session,
                "GET",
                API_URL + "/resources",
                params={"path": path},
                timeout=self._poll_timeout(deadline, context),
            )
            context = f"{target}; last HTTP {response.status_code}"
            if response.status_code == 404 and absent:
                return response
            if response.status_code == 200:
                data = self._json(response)
                if not absent and all(
                    data.get(key) == value for key, value in (expected or {}).items()
                ):
                    return response
            elif response.status_code != 404:
                raise DiskClientError(f"Resource polling returned HTTP {response.status_code}")
            self._pause(deadline, context)
