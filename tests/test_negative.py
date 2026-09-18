import pytest

from tests.helpers import assert_error, put_file, read_file, snapshot, unique_path

pytestmark = [pytest.mark.integration, pytest.mark.negative]


def test_get_nonexistent_resource(api_client, resource_root):
    assert_error(api_client.get_resource(unique_path(resource_root, "missing")), 404)


def test_delete_nonexistent_resource(api_client, resource_root):
    path = unique_path(resource_root, "missing")

    assert_error(api_client.delete_resource(path), 404)
    assert_error(api_client.get_resource(path), 404)


def test_create_without_required_path(api_client):
    assert_error(api_client.create_folder(None), 400)


def test_copy_missing_source_does_not_create_destination(api_client, resource_root):
    source = unique_path(resource_root, "missing")
    destination = unique_path(resource_root, "destination")

    assert_error(api_client.copy_resource(source, destination), 404)

    assert_error(api_client.get_resource(source), 404)
    assert_error(api_client.get_resource(destination), 404)


def test_upload_conflict_preserves_original(api_client, resource_root):
    path = unique_path(resource_root, "protected.txt")
    content = b"original must remain intact\n"
    put_file(api_client, path, content)
    before = snapshot(api_client, path)

    assert_error(api_client.get_upload_link(path, overwrite=False), 409)

    assert snapshot(api_client, path) == before
    assert read_file(api_client, path) == content


@pytest.mark.parametrize("operation", ["copy_resource", "move_resource"], ids=["copy", "move"])
def test_conflict_preserves_both_files(api_client, resource_root, operation):
    source = unique_path(resource_root, "source.txt")
    destination = unique_path(resource_root, "occupied.txt")
    source_content, destination_content = b"source payload\n", b"existing destination payload\n"
    put_file(api_client, source, source_content)
    put_file(api_client, destination, destination_content)
    before = {path: snapshot(api_client, path) for path in (source, destination)}

    response = getattr(api_client, operation)(source, destination, overwrite=False)
    assert_error(response, 409)

    for path, content in ((source, source_content), (destination, destination_content)):
        assert snapshot(api_client, path) == before[path]
        assert read_file(api_client, path) == content
