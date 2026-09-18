import pytest

from tests.helpers import (
    assert_error,
    assert_resource,
    assert_status,
    finish_mutation,
    get_metadata,
    unique_path,
)

pytestmark = pytest.mark.integration


@pytest.mark.smoke
def test_create_folder_and_get_metadata(api_client, resource_root):
    path = unique_path(resource_root, "folder")
    finish_mutation(api_client, api_client.create_folder(path), 201)

    metadata = api_client.wait_resource(path).json()
    assert_resource(metadata, path, "dir")
    assert metadata["_embedded"]["items"] == []


@pytest.mark.parametrize(
    "name",
    ["Папка ё 世界", "folder with spaces", "symbols #&+%=()[]"],
    ids=["unicode", "spaces", "url-special-characters"],
)
def test_resource_name_round_trip(api_client, resource_root, name):
    path = unique_path(resource_root, name)
    finish_mutation(api_client, api_client.create_folder(path), 201)

    assert_resource(api_client.wait_resource(path).json(), path, "dir")
    listing = get_metadata(api_client, resource_root)["_embedded"]["items"]
    assert [item["path"] for item in listing] == [path]


def test_directory_listing_pagination(api_client, resource_root):
    paths = sorted(unique_path(resource_root, name) for name in ("first", "second", "third"))
    for path in paths:
        finish_mutation(api_client, api_client.create_folder(path), 201)
        assert_resource(api_client.wait_resource(path).json(), path, "dir")

    seen = []
    for offset in range(len(paths)):
        response = api_client.get_resource(resource_root, limit=1, offset=offset, sort="name")
        assert_status(response, 200)
        page = response.json()["_embedded"]
        assert page["total"] == len(paths)
        assert page["limit"] == 1
        assert page["offset"] == offset
        assert len(page["items"]) == 1
        assert_resource(page["items"][0], paths[offset], "dir")
        seen.append(page["items"][0]["path"])
    assert seen == paths


def test_metadata_fields_projection(api_client, resource_root):
    response = api_client.get_resource(resource_root, fields="name,path,type")

    assert_status(response, 200)
    assert response.json() == {
        "name": resource_root.rsplit("/", 1)[1],
        "path": resource_root,
        "type": "dir",
    }


@pytest.mark.smoke
def test_delete_empty_folder_and_confirm_absence(api_client, resource_root):
    finish_mutation(api_client, api_client.delete_resource(resource_root), 204)

    assert_error(api_client.wait_resource(resource_root, absent=True), 404)


def test_delete_nonempty_folder_asynchronously(api_client, resource_root):
    child = unique_path(resource_root, "child")
    finish_mutation(api_client, api_client.create_folder(child), 201)
    assert_resource(api_client.wait_resource(child).json(), child, "dir")

    response = api_client.delete_resource(resource_root, force_async=True)
    finish_mutation(api_client, response, 202)

    assert_error(api_client.wait_resource(resource_root, absent=True), 404)
    assert_error(api_client.get_resource(child), 404)
