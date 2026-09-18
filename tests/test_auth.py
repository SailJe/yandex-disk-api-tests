import pytest

from tests.helpers import assert_error, assert_status

pytestmark = [pytest.mark.integration, pytest.mark.auth]


@pytest.mark.smoke
def test_valid_token_can_read_disk_root(api_client):
    response = api_client.get_resource("disk:/", fields="path,type")

    assert_status(response, 200)
    assert response.json() == {"path": "disk:/", "type": "dir"}


@pytest.mark.negative
@pytest.mark.parametrize("unauthorized_client", ["missing", "invalid"], indirect=True)
def test_unauthorized_request_is_rejected(unauthorized_client):
    response = unauthorized_client.get_resource("disk:/", fields="path,type")

    assert_error(response, 401)
