import pytest

from tests.helpers import (
    assert_error,
    assert_file,
    assert_resource,
    file_identity,
    finish_mutation,
    get_metadata,
    put_file,
    read_file,
    unique_path,
)

pytestmark = pytest.mark.integration


@pytest.mark.smoke
def test_upload_small_file_metadata_and_content(api_client, resource_root):
    path = unique_path(resource_root, "Отчёт с пробелами #&+%=.txt")
    content = "API-тест: Привет, 世界!\n".encode()

    metadata = put_file(api_client, path, content)

    assert_file(metadata, path, content)
    assert read_file(api_client, path) == content


def test_upload_overwrite_replaces_content(api_client, resource_root):
    path = unique_path(resource_root, "overwrite.txt")
    original = b"old content\n"
    replacement = b"replacement with a different size\n"
    put_file(api_client, path, original)

    metadata = put_file(api_client, path, replacement, overwrite=True)

    assert_file(metadata, path, replacement)
    assert read_file(api_client, path) == replacement


def test_copy_file_preserves_source(api_client, resource_root):
    source = unique_path(resource_root, "source.txt")
    destination = unique_path(resource_root, "copy.txt")
    content = b"copy this exact payload\n"
    put_file(api_client, source, content)

    finish_mutation(api_client, api_client.copy_resource(source, destination), 201, 202)

    assert_file(api_client.wait_resource(destination).json(), destination, content)
    assert_file(get_metadata(api_client, source), source, content)
    assert read_file(api_client, destination) == read_file(api_client, source) == content


def test_move_file_removes_source(api_client, resource_root):
    source = unique_path(resource_root, "source.txt")
    destination = unique_path(resource_root, "moved.txt")
    content = b"move without losing bytes\n"
    put_file(api_client, source, content)

    response = api_client.move_resource(source, destination, force_async=True)
    finish_mutation(api_client, response, 202)

    assert_file(api_client.wait_resource(destination).json(), destination, content)
    assert_error(api_client.wait_resource(source, absent=True), 404)
    assert read_file(api_client, destination) == content


def test_copy_nonempty_folder_asynchronously(api_client, resource_root):
    source = unique_path(resource_root, "source-folder")
    destination = unique_path(resource_root, "copied-folder")
    finish_mutation(api_client, api_client.create_folder(source), 201)
    child = unique_path(source, "child.txt")
    content = b"nested file\n"
    put_file(api_client, child, content)

    response = api_client.copy_resource(source, destination, force_async=True)
    finish_mutation(api_client, response, 202)

    assert_resource(api_client.wait_resource(destination).json(), destination, "dir")
    copied_child = destination + "/" + child.rsplit("/", 1)[1]
    assert_file(
        api_client.wait_resource(copied_child, expected=file_identity(content)).json(),
        copied_child,
        content,
    )
    assert_resource(get_metadata(api_client, source), source, "dir")
    assert_file(get_metadata(api_client, child), child, content)
    assert read_file(api_client, copied_child) == content
