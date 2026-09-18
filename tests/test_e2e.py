import pytest

from tests.helpers import (
    assert_error,
    assert_file,
    assert_status,
    finish_mutation,
    get_metadata,
    put_file,
    read_file,
    unique_path,
)

pytestmark = [pytest.mark.integration, pytest.mark.e2e]


def test_file_lifecycle(api_client, resource_root):
    original = unique_path(resource_root, "жизненный цикл.txt")
    copied = unique_path(resource_root, "copy.txt")
    moved = unique_path(resource_root, "moved.txt")
    content = "Начало → копирование → перемещение → удаление\n".encode()
    put_file(api_client, original, content)

    finish_mutation(api_client, api_client.copy_resource(original, copied), 201, 202)
    assert_file(api_client.wait_resource(copied).json(), copied, content)
    assert_file(get_metadata(api_client, original), original, content)

    response = api_client.move_resource(copied, moved, force_async=True)
    finish_mutation(api_client, response, 202)
    assert_error(api_client.wait_resource(copied, absent=True), 404)
    assert_file(api_client.wait_resource(moved).json(), moved, content)
    assert read_file(api_client, moved) == content

    for path in (original, moved):
        finish_mutation(api_client, api_client.delete_resource(path), 204)
        assert_error(api_client.wait_resource(path, absent=True), 404)

    response = api_client.get_resource(resource_root)
    assert_status(response, 200)
    assert response.json()["_embedded"]["items"] == []
