from app import api


def test_bundle_key_changes_when_folder_changes() -> None:
    # Arrange
    req_one = api.CreateBundleRequest(
        folder_name="folder-a",
        compression="zip",
        urls=["https://example.com/file.txt"],
    )
    req_two = api.CreateBundleRequest(
        folder_name="folder-b",
        compression="zip",
        urls=["https://example.com/file.txt"],
    )

    # Act
    key_one = api._bundle_key(req_one)
    key_two = api._bundle_key(req_two)

    # Assert
    assert key_one != key_two

    # Cleanup
    # No cleanup needed; this test only computes deterministic keys.


def test_bundle_key_ignores_volatile_presigned_query_params() -> None:
    # Arrange
    req_one = api.CreateBundleRequest(
        folder_name="same-folder",
        compression="zip",
        urls=["https://example.com/file.txt?x=1&X-Amz-Date=111&X-Amz-Signature=aaa"],
    )
    req_two = api.CreateBundleRequest(
        folder_name="same-folder",
        compression="zip",
        urls=["https://example.com/file.txt?X-Amz-Date=999&x=1&X-Amz-Signature=bbb"],
    )

    # Act
    key_one = api._bundle_key(req_one)
    key_two = api._bundle_key(req_two)

    # Assert
    assert key_one == key_two

    # Cleanup
    # No cleanup needed; this test only computes deterministic keys.

