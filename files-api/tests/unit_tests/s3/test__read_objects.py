"""Test cases for `s3.read_objects`."""

import boto3
from files_api.s3.read_objects import fetch_s3_objects_metadata, fetch_s3_objects_using_page_token, object_exists_in_s3
from tests.consts import TEST_BUCKET_NAME


def test_object_exists_in_s3(mocked_aws: None):
    """Test checking if an object exists in an S3 bucket."""
    s3_client = boto3.client("s3")
    s3_client.put_object(Bucket=TEST_BUCKET_NAME, Key="testfile.txt", Body=b"test content")
    assert object_exists_in_s3(TEST_BUCKET_NAME, "testfile.txt")
    assert not object_exists_in_s3(TEST_BUCKET_NAME, "non-existent.txt")


def test_pagination(mocked_aws: None):
    """Test paginating through objects in an S3 bucket."""
    s3_client = boto3.client("s3")

    # Create 5 objects in the bucket
    for i in range(1, 6):
        s3_client.put_object(Bucket=TEST_BUCKET_NAME, Key=f"testfile{i}.txt", Body=f"test content {i}")

    # Paginate 2 objects at a time
    max_pages = 2
    files, next_page_token = fetch_s3_objects_metadata(bucket_name=TEST_BUCKET_NAME, max_keys=max_pages)
    assert len(files) == 2
    assert files[0]["Key"] == "testfile1.txt"
    assert files[1]["Key"] == "testfile2.txt"

    # Fetch the next page
    files, next_page_token = fetch_s3_objects_using_page_token(
        bucket_name=TEST_BUCKET_NAME,
        continuation_token=next_page_token,
        max_keys=max_pages,
    )
    assert len(files) == 2
    assert files[0]["Key"] == "testfile3.txt"
    assert files[1]["Key"] == "testfile4.txt"

    # Fetch the last page
    files, next_page_token = fetch_s3_objects_using_page_token(
        bucket_name=TEST_BUCKET_NAME,
        continuation_token=next_page_token,
        max_keys=max_pages,
    )
    assert len(files) == 1
    assert files[0]["Key"] == "testfile5.txt"
    assert next_page_token is None


def test_mixed_page_sizes(mocked_aws: None):
    """Test paginating through objects in an S3 bucket with mixed page sizes."""
    s3_client = boto3.client("s3")

    # Create 5 objects in the bucket
    for i in range(1, 7):
        s3_client.put_object(Bucket=TEST_BUCKET_NAME, Key=f"testfile{i}.txt", Body=f"test content {i}")

    # Paginate with mixed page sizes
    files, next_page_token = fetch_s3_objects_metadata(bucket_name=TEST_BUCKET_NAME, max_keys=3)
    assert len(files) == 3
    assert files[0]["Key"] == "testfile1.txt"
    assert files[1]["Key"] == "testfile2.txt"
    assert files[2]["Key"] == "testfile3.txt"

    # Fetch the next page
    files, next_page_token = fetch_s3_objects_using_page_token(
        bucket_name=TEST_BUCKET_NAME, continuation_token=next_page_token, max_keys=1
    )
    assert len(files) == 1
    assert files[0]["Key"] == "testfile4.txt"

    # Fetch the last page
    files, next_page_token = fetch_s3_objects_using_page_token(
        bucket_name=TEST_BUCKET_NAME, continuation_token=next_page_token, max_keys=2
    )
    assert len(files) == 2
    assert files[0]["Key"] == "testfile5.txt"
    assert files[1]["Key"] == "testfile6.txt"
    assert next_page_token is None


def test_directory_queries(mocked_aws: None):  # noqa: R701
    """Test querying objects in an S3 bucket with directory-like structure."""
    s3_client = boto3.client("s3")

    # Create a directory-like structure in the bucket
    s3_client.put_object(Bucket=TEST_BUCKET_NAME, Key="folder1/file1.txt", Body="content 1")
    s3_client.put_object(Bucket=TEST_BUCKET_NAME, Key="folder1/file2.txt", Body="content 2")
    s3_client.put_object(Bucket=TEST_BUCKET_NAME, Key="folder2/file3.txt", Body="content 3")
    s3_client.put_object(Bucket=TEST_BUCKET_NAME, Key="folder2/subfolder1/file4.txt", Body="content 4")
    s3_client.put_object(Bucket=TEST_BUCKET_NAME, Key="file5.txt", Body="content 5")

    # Query with prefix
    files, next_page_token = fetch_s3_objects_metadata(bucket_name=TEST_BUCKET_NAME, prefix="folder1/")
    assert len(files) == 2
    assert files[0]["Key"] == "folder1/file1.txt"
    assert files[1]["Key"] == "folder1/file2.txt"
    assert next_page_token is None

    # Query with prefix for a subfolder
    files, next_page_token = fetch_s3_objects_metadata(bucket_name=TEST_BUCKET_NAME, prefix="folder2/subfolder1/")
    assert len(files) == 1
    assert files[0]["Key"] == "folder2/subfolder1/file4.txt"
    assert next_page_token is None

    # Query with no prefix
    files, next_page_token = fetch_s3_objects_metadata(bucket_name=TEST_BUCKET_NAME)
    assert len(files) == 5
    assert files[0]["Key"] == "file5.txt"
    assert files[1]["Key"] == "folder1/file1.txt"
    assert files[2]["Key"] == "folder1/file2.txt"
    assert files[3]["Key"] == "folder2/file3.txt"
    assert files[4]["Key"] == "folder2/subfolder1/file4.txt"
    assert next_page_token is None
