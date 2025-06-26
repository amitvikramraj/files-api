"""Unit tests for the error cases of the API routes."""

from fastapi import status
from fastapi.testclient import TestClient
from files_api.schemas import DEFAULT_GET_FILES_MAX_PAGE_SIZE

from tests.consts import TEST_BUCKET_NAME
from tests.utils import delete_s3_bucket

NON_EXISTENT_FILE_PATH = "nonexistent_file.txt"


def test_get_nonexistent_file(client: TestClient):
    """Test that a 404 error is returned when trying to get a nonexistent file."""
    response = client.get(f"/v1/files/{NON_EXISTENT_FILE_PATH}")
    assert response.status_code == status.HTTP_404_NOT_FOUND
    assert response.json() == {"detail": f"File not found: {NON_EXISTENT_FILE_PATH}"}


def test_get_nonexistent_file_metadata(client: TestClient):
    """Test that a 404 error is returned when trying to get metadata for a nonexistent file."""
    response = client.head(f"/v1/files/{NON_EXISTENT_FILE_PATH}")
    assert response.status_code == status.HTTP_404_NOT_FOUND
    assert response.headers["X-Error"] == f"File not found: {NON_EXISTENT_FILE_PATH}"


def test_delete_nonexistent_file(client: TestClient):
    """Test that a 404 error is returned when trying to delete a nonexistent file."""
    response = client.delete(f"/v1/files/{NON_EXISTENT_FILE_PATH}")
    assert response.status_code == status.HTTP_404_NOT_FOUND
    assert response.headers["X-Error"] == f"File not found: {NON_EXISTENT_FILE_PATH}"


def test_get_files_invalid_page_size(client: TestClient):
    """Test that a 422 Unprocessable Entity error is returned when an invalid page size is provided."""
    # Test negative page size
    response = client.get("/v1/files?page_size=-1")
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

    # Test page size greater than the maximum allowed
    response = client.get(f"/v1/files?page_size={DEFAULT_GET_FILES_MAX_PAGE_SIZE + 1}")
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


def test_get_files_page_token_is_mutually_exclusive_with_page_size_and_directory(
    client: TestClient,
):
    """Test that a 422 Unprocessable Entity error is returned when page_token is provided with page_size or directory."""
    response = client.get("/v1/files?page_token=token&directory=dir")
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    assert "mutually exclusive" in str(response.json())

    response = client.get("/v1/files?page_token=token&page_size=11&directory=dir")
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    assert "mutually exclusive" in str(response.json())


def test_unforeseen_500_error(client: TestClient):
    """Test that a 500 Internal Server Error is returned when an unforeseen error occurs."""
    # Delete the S3 bucket and all objects inside name from the app state to force an unforeseen error
    delete_s3_bucket(TEST_BUCKET_NAME)

    # make a request to the API to a route that interacts with the S3 bucket
    response = client.get("/v1/files")
    assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
