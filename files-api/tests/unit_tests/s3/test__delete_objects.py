"""Test cases for `s3.delete_objects`."""

import boto3
from files_api.s3.delete_objects import delete_s3_object
from files_api.s3.read_objects import object_exists_in_s3
from files_api.s3.write_objects import upload_s3_object
from tests.consts import TEST_BUCKET_NAME


def test_delete_existing_s3_object(mocked_aws: None):
    """Test deleting an existing object from an S3 bucket."""
    s3_client = boto3.client("s3")
    # Create a file in the bucket
    s3_client.put_object(Bucket=TEST_BUCKET_NAME, Key="testfile-exists.txt", Body=b"test content")
    # delete the file
    delete_s3_object(bucket_name=TEST_BUCKET_NAME, object_key="testfile-exists.txt")
    # Check the contents of the bucket, should be empty
    assert not s3_client.list_objects_v2(Bucket=TEST_BUCKET_NAME).get("Contents")


def test_delete_nonexistent_s3_object(mocked_aws: None):
    """Test deleting a non-existent object from an S3 bucket."""
    # Create a file in the bucket
    upload_s3_object(
        bucket_name=TEST_BUCKET_NAME,
        object_key="testfile-exists.txt",
        file_content=b"test content",
    )
    # delete the file
    delete_s3_object(bucket_name=TEST_BUCKET_NAME, object_key="testfile-exists.txt")
    # delete the file again
    delete_s3_object(bucket_name=TEST_BUCKET_NAME, object_key="testfile-exists.txt")
    # check if the file exists, should return False
    assert not object_exists_in_s3(bucket_name=TEST_BUCKET_NAME, object_key="testfile-exists.txt")
