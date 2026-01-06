"""FastAPI application for managing files in an S3 bucket."""

import mimetypes
from typing import Annotated

import requests  # type: ignore
from fastapi import (
    APIRouter,
    Body,
    Depends,
    File,
    HTTPException,
    Path,
    Request,
    Response,
    UploadFile,
    status,
)
from fastapi.responses import StreamingResponse
from loguru import logger

from files_api.generate_files.openai import (
    generate_image,
    generate_text_to_speech,
    get_text_chat_completion,
)
from files_api.route_handler import RouteHandler
from files_api.s3.delete_objects import delete_s3_object
from files_api.s3.read_objects import (
    fetch_s3_object,
    fetch_s3_objects_metadata,
    fetch_s3_objects_using_page_token,
    object_exists_in_s3,
)
from files_api.s3.write_objects import upload_s3_object
from files_api.schemas import (
    FileMetadata,
    GeneratedFileType,
    GenerateFilesBody,
    GetFilesQueryParams,
    GetFilesResponse,
    PostFileResponse,
    PutFileResponse,
)
from files_api.settings import Settings

ROUTER = APIRouter()
ROUTER.route_class = RouteHandler


@ROUTER.put(
    "/v1/files/{file_path:path}",
    status_code=status.HTTP_201_CREATED,
    tags=["Files"],
    summary="Upload or Update a File",
    responses={
        status.HTTP_201_CREATED: {
            "model": PutFileResponse,
            "description": "File uploaded successfully.",
            "content": PutFileResponse.model_json_schema()[str(status.HTTP_201_CREATED)]["content"],
        },
        status.HTTP_200_OK: {
            "model": PutFileResponse,
            "description": "File updated successfully.",
            "content": PutFileResponse.model_json_schema()[str(status.HTTP_200_OK)]["content"],
        },
    },
)
async def upload_file(
    request: Request,
    response: Response,
    file_path: Annotated[str, Path(description=PutFileResponse.model_fields["file_path"].description)],
    file_content: Annotated[UploadFile, File(description="The file to upload.")],
) -> PutFileResponse:
    """Upload or Update a File."""
    settings: Settings = request.app.state.settings
    s3_bucket_name = settings.s3_bucket_name
    object_already_exists = object_exists_in_s3(bucket_name=s3_bucket_name, object_key=file_path)

    logger.debug("object_already_exists = {exists}", exists=object_already_exists)
    if object_already_exists:
        response_message = f"Existing file updated at path: {file_path}"
        logger.info(f"File updated successfully: {file_path}")
        response.status_code = status.HTTP_200_OK
    else:
        response_message = f"New file uploaded at path: {file_path}"
        logger.info(f"File uploaded successfully: {file_path}")
        response.status_code = status.HTTP_201_CREATED

    file_bytes: bytes = await file_content.read()
    logger.debug("Trying to upload the file to S3: {file_path}", file_path=file_path)
    upload_s3_object(
        bucket_name=s3_bucket_name,
        object_key=file_path,
        file_content=file_bytes,
        content_type=file_content.content_type,
    )
    return PutFileResponse(file_path=file_path, message=response_message)


@ROUTER.get(
    "/v1/files",
    tags=["Files"],
    summary="List Files",
    responses={
        status.HTTP_200_OK: {
            "model": GetFilesResponse,
            "description": "Successful Response",
            "content": {
                "application/json": {
                    "examples": {
                        "With Pagination": GetFilesResponse.model_json_schema()["examples"][0],
                        "No Pages Left": GetFilesResponse.model_json_schema()["examples"][1],
                    },
                },
            },
        },
    },
)
async def list_files(
    request: Request, response: Response, query_params: Annotated[GetFilesQueryParams, Depends()]
) -> GetFilesResponse:
    """List Files with Pagination."""
    settings: Settings = request.app.state.settings
    s3_bucket_name = settings.s3_bucket_name

    logger.debug("fetching files from s3: {dir}", dir=query_params.directory)
    logger.info("query_params = {query_params}", query_params=query_params.model_dump_json())

    if query_params.page_token:
        files, next_page_token = fetch_s3_objects_using_page_token(
            bucket_name=s3_bucket_name,
            continuation_token=query_params.page_token,
            max_keys=query_params.page_size,
        )
    else:
        files, next_page_token = fetch_s3_objects_metadata(
            bucket_name=s3_bucket_name,
            prefix=query_params.directory,
            max_keys=query_params.page_size,
        )

    files_metadata = [
        FileMetadata(
            file_path=file["Key"],
            last_modified=file["LastModified"],
            size_bytes=file["Size"],
        )
        for file in files
    ]

    logger.info(f"Files retrieved successfully: {len(files_metadata)} files")
    response.status_code = status.HTTP_200_OK
    return GetFilesResponse(
        files=files_metadata,
        next_page_token=next_page_token if next_page_token else None,
    )


@ROUTER.head(
    "/v1/files/{file_path:path}",
    tags=["Files"],
    summary="Retrieve File Metadata",
    responses={
        status.HTTP_404_NOT_FOUND: {
            "description": "File not found for the given `file_path`.",
            "headers": {
                "X-Error": {
                    "description": "Error message indicating the file was not found.",
                    "example": "File not found: `path/to/file.txt`",
                    "schema": {"type": "string", "format": "text"},
                }
            },
            "content": None,
        },
        status.HTTP_200_OK: {
            "description": "Successful Response",
            "headers": {
                "Content-Type": {
                    "description": "The [MIME type](https://developer.mozilla.org/en-US/docs/Web/HTTP/Basics_of_HTTP/MIME_types/Common_types) of the file.",
                    "example": "text/plain",
                    "schema": {"type": "string", "format": "text"},
                },
                "Content-Length": {
                    "description": "The size of the file in bytes.",
                    "example": 512,
                    "schema": {"type": "integer", "format": "integer"},
                },
                "Last-Modified": {
                    "description": "The last modified date of the file.",
                    "example": "Thu, 01 Jan 2022 00:00:00 GMT",
                    "schema": {"type": "string", "format": "date-time"},
                },
            },
            "content": None,
        },
    },
)
async def get_file_metadata(file_path: str, request: Request, response: Response) -> Response:
    """
    Retrieve File Metadata.

    Note: by convention, HEAD requests MUST NOT return a body in the response.
    """
    settings: Settings = request.app.state.settings
    s3_bucket_name = settings.s3_bucket_name
    object_exists = object_exists_in_s3(bucket_name=s3_bucket_name, object_key=file_path)

    logger.debug("object_exists_in_s3 = {exists}", exists=object_exists)
    if not object_exists:
        logger.error(f"File not found: {file_path}")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            headers={"X-Error": f"File not found: {file_path}"},
        )

    logger.debug("Trying to retrieve metadata for the file: {file_path}", file_path=file_path)
    get_object_response = fetch_s3_object(bucket_name=s3_bucket_name, object_key=file_path)

    logger.info(f"File metadata retrieved successfully: {file_path}")
    response.headers["Content-Type"] = get_object_response["ContentType"]
    response.headers["Content-Length"] = str(get_object_response["ContentLength"])
    response.headers["Last-Modified"] = get_object_response["LastModified"].strftime("%a, %d %b %Y %H:%M:%S GMT")
    response.status_code = status.HTTP_200_OK

    return response


@ROUTER.get(
    "/v1/files/{file_path:path}",
    tags=["Files"],
    summary="Retrieve a File",
    responses={
        status.HTTP_404_NOT_FOUND: {
            "description": "File not found for the given `file_path`.",
            "content": {
                "application/json": {
                    "example": {"detail": "File not found: path/to/file.txt"},
                },
            },
        },
        status.HTTP_200_OK: {
            "description": "Successful Response",
            "content": {
                "text/plain": {
                    "schema": {"type": "string", "format": "text"},
                    "example": "File Content.",
                },
                "application/octet-stream": {
                    "schema": {"type": "string", "format": "binary"},
                },
                "application/json": None,
            },
            "headers": {
                "Content-Type": {
                    "description": "The [MIME type](https://developer.mozilla.org/en-US/docs/Web/HTTP/Basics_of_HTTP/MIME_types/Common_types) of the file.",
                    "example": "text/plain",
                    "schema": {"type": "string"},
                },
                "Content-Length": {
                    "description": "The size of the file in bytes.",
                    "example": 512,
                    "schema": {"type": "integer"},
                },
            },
        },
    },
)
async def get_file(
    request: Request, response: Response, file_path: Annotated[str, Path(description="The path to the file.")]
) -> StreamingResponse:
    """Retrieve a File."""
    settings: Settings = request.app.state.settings
    s3_bucket_name = settings.s3_bucket_name
    object_exists = object_exists_in_s3(bucket_name=s3_bucket_name, object_key=file_path)

    logger.debug("object_exists_in_s3 = {exists}", exists=object_exists)
    if not object_exists:
        logger.error(f"File not found: {file_path}")
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"File not found: {file_path}")

    logger.debug("Trying to retrieve the file: {file_path}", file_path=file_path)
    get_object_response = fetch_s3_object(bucket_name=s3_bucket_name, object_key=file_path)

    response.headers["Content-Type"] = get_object_response["ContentType"]
    response.headers["Content-Length"] = str(get_object_response["ContentLength"])
    # If the file is a PDF, set the Content-Disposition header to force download
    if response.headers["Content-Type"] == "application/pdf":
        logger.info("Setting Content-Disposition header to force download for PDF file.")
        response.headers["Content-Disposition"] = f'attachment; filename="{file_path}"'
        # response.headers["Access-Control-Expose-Headers"] = "Content-Disposition"

    response.status_code = status.HTTP_200_OK

    logger.info(f"File retrieved successfully: {file_path}")
    return StreamingResponse(
        content=get_object_response["Body"],
        media_type=get_object_response["ContentType"],
        headers=response.headers,
    )


@ROUTER.delete(
    "/v1/files/{file_path:path}",
    tags=["Files"],
    summary="Delete a File",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={
        status.HTTP_204_NO_CONTENT: {"description": "File deleted successfully."},
        status.HTTP_404_NOT_FOUND: {"description": "File not found."},
    },
)
async def delete_file(
    request: Request, response: Response, file_path: Annotated[str, Path(description="The path to the file.")]
) -> Response:
    """
    Delete a file.

    NOTE: DELETE requests MUST NOT return a body in the response.
    """
    settings: Settings = request.app.state.settings
    s3_bucket_name = settings.s3_bucket_name
    object_exists = object_exists_in_s3(bucket_name=s3_bucket_name, object_key=file_path)

    logger.debug("object_exists_in_s3 = {exists}", exists=object_exists)
    if not object_exists:
        logger.error(f"Cannot delete file, file not found: {file_path}")
        response.status_code = status.HTTP_404_NOT_FOUND
        response.headers["X-Error"] = f"File not found: {file_path}"
        return response

    logger.debug("Trying to delete the file in S3: {file_path}", file_path=file_path)
    delete_s3_object(bucket_name=s3_bucket_name, object_key=file_path)
    logger.info(f"File deleted successfully at {file_path}")
    response.status_code = status.HTTP_204_NO_CONTENT
    return response


@ROUTER.post(
    "/v1/files/generated",
    status_code=status.HTTP_201_CREATED,
    tags=["Generate Files"],
    summary="AI Generated Files",
    responses={
        status.HTTP_201_CREATED: {
            "model": PostFileResponse,
            "description": "Successful Response",
            "content": {
                "application/json": {
                    "examples": {
                        GeneratedFileType.TEXT: PostFileResponse.model_json_schema()["examples"][0],
                        GeneratedFileType.IMAGE: PostFileResponse.model_json_schema()["examples"][1],
                        GeneratedFileType.AUDIO: PostFileResponse.model_json_schema()["examples"][2],
                    },
                },
            },
        },
        status.HTTP_400_BAD_REQUEST: {
            "model": PostFileResponse,
            "description": "File already exists.",
            "content": {
                "application/json": {
                    "example": {
                        "file_path": "path/to/file.txt",
                        "message": "File already exists. Please use a different file name.",
                    },
                },
            },
        },
    },
)
async def generate_file_using_openai(
    request: Request,
    response: Response,
    body: GenerateFilesBody = Body(...),  # noqa: B008
) -> PostFileResponse:
    """
    Generate a File using AI.

    ```
    Supported file types(Case):
    - Text: .txt
    - Image: .png, .jpg, .jpeg
    - Text-to-Speech: .mp3, .opus, .aac, .flac, .wav, .pcm
    ```
    """
    settings: Settings = request.app.state.settings
    s3_bucket_name = settings.s3_bucket_name
    content_type = None  # Set the content type to None initially

    # Check if the file already exists
    object_exists = object_exists_in_s3(bucket_name=s3_bucket_name, object_key=body.file_path)
    logger.debug("object_exists_in_s3 = {exists}", exists=object_exists)
    if object_exists:
        logger.error(f"File already exists: {body.file_path}")
        response.status_code = status.HTTP_400_BAD_REQUEST
        return PostFileResponse(
            file_path=body.file_path, message="File already exists. Please use a different file name."
        )

    # Generate the file based on the file type
    logger.debug("Trying to generate content using OpenAI, request_body = {body}", body=body.model_dump_json())
    if body.file_type == GeneratedFileType.TEXT:
        file_content = await get_text_chat_completion(prompt=body.prompt)
        file_content_bytes: bytes = file_content.encode("utf-8")  # convert string to bytes
        content_type = "text/plain"
    elif body.file_type == GeneratedFileType.IMAGE:
        image_url = await generate_image(prompt=body.prompt)
        # Download the image from the URL
        image_response = requests.get(image_url)  # pylint: disable=missing-timeout
        file_content_bytes = image_response.content

        # For Gemini image generation:
        # image_bytes = await generate_image(prompt=body.prompt)
        # if image_bytes is None:
        #     raise ValueError("Failed to generate image from Gemini")
        # file_content_bytes = image_bytes

        logger.debug("Image file generated successfully, image_url: {image_url}", image_url=image_url)
    else:
        response_format = body.file_path.split(".")[-1]
        file_content_bytes, content_type = await generate_text_to_speech(
            prompt=body.prompt,
            response_format=response_format,  # type: ignore
        )

    # If content_type is None, try to guess it from the file path
    content_type: str | None = content_type or mimetypes.guess_type(body.file_path)[0]  # type: ignore
    logger.debug(f"Content-Type for the generated file: {content_type}")

    # Upload the generated file to S3
    logger.debug("Trying to upload the generated file to S3: {file_path}", file_path=body.file_path)
    upload_s3_object(
        bucket_name=s3_bucket_name,
        object_key=body.file_path,
        file_content=file_content_bytes,
        content_type=content_type,
    )

    logger.info("Generated file uploaded successfully at path: {file_path}", file_path=body.file_path)
    response.status_code = status.HTTP_201_CREATED
    return PostFileResponse(
        file_path=body.file_path,
        message=f"New {body.file_type.value} file generated and uploaded at path: {body.file_path}",
    )
