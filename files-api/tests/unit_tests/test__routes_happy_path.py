"""Unit tests for the main FastAPI application."""

from fastapi import status
from fastapi.testclient import TestClient

TEST_FILE_PATH = "some/nested/path/file.txt"
TEST_FILE_CONTENT = b"Hello, world!"
TEST_FILE_CONTENT_TYPE = "text/plain"


def test_upload_file(client: TestClient):
    """Test uploading/updating a file to the bucket using PUT method."""
    response = client.put(
        f"/v1/files/{TEST_FILE_PATH}",
        files={"file_content": (TEST_FILE_PATH, TEST_FILE_CONTENT, TEST_FILE_CONTENT_TYPE)},
    )

    assert response.status_code == status.HTTP_201_CREATED
    assert response.json() == {
        "file_path": TEST_FILE_PATH,
        "message": f"New file uploaded at path: {TEST_FILE_PATH}",
    }

    # update the file
    updated_content = b"Hello, world! Updated!"
    response = client.put(
        f"/v1/files/{TEST_FILE_PATH}",
        files={"file_content": (TEST_FILE_PATH, updated_content, TEST_FILE_PATH)},
    )

    assert response.status_code == status.HTTP_200_OK
    assert response.json() == {
        "file_path": TEST_FILE_PATH,
        "message": f"Existing file updated at path: {TEST_FILE_PATH}",
    }


def test_list_files_with_pagination(client: TestClient):
    """Test listing files with pagination using GET method."""
    # Upload files
    for i in range(15):
        client.put(
            f"/v1/files/file{i}.txt",
            files={
                "file_content": (
                    f"file{i}.txt",
                    TEST_FILE_CONTENT,
                    TEST_FILE_CONTENT_TYPE,
                )
            },
        )
    # List files with page size 10
    response = client.get("/v1/files?page_size=10")
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert len(data["files"]) == 10
    assert "next_page_token" in data


def test_get_file_metadata(client: TestClient):
    """Test getting metadata for a file using HEAD method."""
    # Create sample file
    client.put(
        url=f"/v1/files/{TEST_FILE_PATH}",
        files={
            "file_content": (
                "folder1/file1.txt",
                TEST_FILE_CONTENT,
                TEST_FILE_CONTENT_TYPE,
            )
        },
    )

    # Query metadata for existing file
    response = client.head(f"/v1/files/{TEST_FILE_PATH}")
    assert response.status_code == status.HTTP_200_OK
    assert response.headers["Content-Type"] == TEST_FILE_CONTENT_TYPE
    assert response.headers["Content-Length"] == str(len(TEST_FILE_CONTENT))


def test_get_file(client: TestClient):
    """Test getting a file using GET method."""
    # Create sample file
    client.put(
        url=f"/v1/files/{TEST_FILE_PATH}",
        files={
            "file_content": (
                "folder1/file1.txt",
                TEST_FILE_CONTENT,
                TEST_FILE_CONTENT_TYPE,
            )
        },
    )

    # Query a existing file
    response = client.get(f"/v1/files/{TEST_FILE_PATH}")
    assert response.status_code == status.HTTP_200_OK
    assert response.headers["Content-Type"] == TEST_FILE_CONTENT_TYPE
    assert response.headers["Content-Length"] == str(len(TEST_FILE_CONTENT))
    assert response.content == TEST_FILE_CONTENT


def test_delete_file(client: TestClient):
    """Test deleting a file using DELETE method."""
    # Create sample file
    client.put(
        url=f"/v1/files/{TEST_FILE_PATH}",
        files={
            "file_content": (
                "folder1/file1.txt",
                TEST_FILE_CONTENT,
                TEST_FILE_CONTENT_TYPE,
            )
        },
    )

    # Delete existing file
    response = client.delete(f"/v1/files/{TEST_FILE_PATH}")
    assert response.status_code == status.HTTP_204_NO_CONTENT
