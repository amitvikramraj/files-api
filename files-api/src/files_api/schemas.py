"""FastAPI application for managing files in an S3 bucket."""

import re
from datetime import datetime
from enum import Enum
from typing import List, Optional

from fastapi import Path, status
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from typing_extensions import Self

DEFAULT_GET_FILES_PAGE_SIZE = 10
DEFAULT_GET_FILES_MIN_PAGE_SIZE = 1
DEFAULT_GET_FILES_MAX_PAGE_SIZE = 100
DEFAULT_GET_FILES_DIRECTORY = ""


# from pydantic.alias_generators import to_camel
# class BaseSchema(BaseModel):
#     model_config = ConfigDict(
#         alias_generator=to_camel,
#         populate_by_name=True,
#     )


# read (cRud)
class FileMetadata(BaseModel):
    """`Metadata` of a file."""

    file_path: str = Field(
        description="The path to the file.",
        json_schema_extra={"example": "path/to/file.txt"},
    )
    last_modified: datetime = Field(
        description="The last modified timestamp of the file.",
        json_schema_extra={"example": "2021-09-01T12:00:00"},
    )
    size_bytes: int = Field(
        description="The size of the file in bytes.",
        json_schema_extra={"example": 512},
    )


# create/update (Crud)
class PutFileResponse(BaseModel):
    """Response model for `PUT /v1/files/:file_path`."""

    file_path: str = Field(
        description="The path to the file.",
        json_schema_extra={"example": "path/to/file.txt"},
    )
    message: str = Field(
        description="The message indicating the status of the operation.",
        json_schema_extra={"example": "New file uploaded at path: path/to/file.txt"},
    )

    model_config = ConfigDict(
        json_schema_extra={
            f"{status.HTTP_201_CREATED}": {
                "content": {
                    "application/json": {
                        "example": {
                            "file_path": "path/to/file.txt",
                            "message": "New file uploaded at path: path/to/file.txt",
                        },
                    },
                },
            },
            f"{status.HTTP_200_OK}": {
                "content": {
                    "application/json": {
                        "example": {
                            "file_path": "path/to/file.txt",
                            "message": "Existing file updated at path: path/to/file.txt",
                        }
                    },
                },
            },
        }
    )


# read (cRud)
class GetFilesQueryParams(BaseModel):
    """Query parameters for `GET /v1/files`."""

    page_size: int = Field(
        default=DEFAULT_GET_FILES_PAGE_SIZE,
        ge=DEFAULT_GET_FILES_MIN_PAGE_SIZE,
        le=DEFAULT_GET_FILES_MAX_PAGE_SIZE,
        description="The number of files to return in a single page.",
        json_schema_extra={"example": 10},
    )
    directory: Optional[str] = Field(
        default=DEFAULT_GET_FILES_DIRECTORY,
        description="The directory to list files from.",
        json_schema_extra={"example": "path/to/directory"},
    )
    page_token: Optional[str] = Field(
        default=None,
        description="The token to retrieve the next page of files.",
        json_schema_extra={"example": "next_page_token_value"},
    )

    @model_validator(mode="after")
    def check_page_token(self) -> Self:
        """Ensure that page_token is mutually exclusive with page_size and directory."""
        if self.page_token:
            get_files_query_params: dict = self.model_dump(exclude_defaults=True)
            directory_set: bool = "directory" in get_files_query_params.keys()
            if directory_set:
                raise ValueError("page_token is mutually exclusive with directory")
        return self


# read (cRud)
class GetFilesResponse(BaseModel):
    """Response model for `GET /v1/files/:file_path`."""

    files: List[FileMetadata]
    next_page_token: Optional[str]

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "value": {
                        "files": [
                            {
                                "file_path": "path/to/file1.txt",
                                "last_modified": "2021-09-01T12:00:00",
                                "size_bytes": 512,
                            },
                            {
                                "file_path": "path/to/file2.txt",
                                "last_modified": "2021-09-02T12:00:00",
                                "size_bytes": 256,
                            },
                        ],
                        "next_page_token": "next_page_token_value",
                    }
                },
                {
                    "value": {
                        "files": [
                            {
                                "file_path": "path/to/file1.txt",
                                "last_modified": "2021-09-01T12:00:00",
                                "size_bytes": 512,
                            },
                            {
                                "file_path": "path/to/file2.txt",
                                "last_modified": "2021-09-02T12:00:00",
                                "size_bytes": 256,
                            },
                        ],
                        "next_page_token": "null",
                    }
                },
            ]
        }
    )


# delete (cruD)
class DeleteFileResponse(BaseModel):
    """Response model for `DELETE /v1/files/:file_path`."""

    message: str


class GeneratedFileType(str, Enum):
    """The type of file generated by OpenAI."""

    TEXT = "Text"
    IMAGE = "Image"
    AUDIO = "Text-to-Speech"

    @classmethod
    def from_string(cls, value: str) -> "GeneratedFileType":
        """Convert a string to a case-insensitive `GeneratedFileType`."""
        value_lower = value.lower()
        for item in cls:
            if item.value.lower() == value_lower:
                return item
        raise ValueError(f"Invalid file type: {value}; Expected one of: {', '.join(item.value for item in cls)}")


class GenerateFilesBody(BaseModel):
    """Request Body for `POST /v1/files/generated`."""

    file_path: str = Path(
        ...,
        description="The path to the file to generate.",
        json_schema_extra={"example": "path/to/file.txt"},
        # pattern="^.*\.(txt|png|jpg|jpeg|mp3|opus|aac|flac|wav|pcm)$",
    )
    prompt: str = Field(
        ...,
        description="The prompt to generate the file content.",
        json_schema_extra={"example": "Generate a text file."},
    )
    file_type: GeneratedFileType = Field(
        ...,
        description="The type of file to generate.(case in-sensitive)",
        json_schema_extra={"example": "Text"},
    )

    # https://docs.pydantic.dev/latest/concepts/validators/#field-validators
    @field_validator("file_type", mode="before")
    @classmethod
    def normalize_file_type(cls, value: str) -> str:
        """Normalize file_type to make it case-insensitive."""
        value = GeneratedFileType.from_string(value)
        return value

    @model_validator(mode="after")
    def validate_file_path(self) -> Self:
        """Ensure that the file path matches the file type."""
        file_type = self.file_type

        if file_type == GeneratedFileType.TEXT and not re.match(r".*\.txt$", self.file_path):
            raise ValueError("For text files, the path must end with .txt")

        if file_type == GeneratedFileType.IMAGE and not re.match(r".*\.(png|jpg|jpeg)$", self.file_path):
            raise ValueError("For image files, the path must end with .png, .jpg, or .jpeg")

        if file_type == GeneratedFileType.AUDIO and not re.match(r".*\.(mp3|opus|aac|flac|wav|pcm)$", self.file_path):
            raise ValueError("For audio files, the path must end with .mp3, .opus, .aac, .flac, .wav, or .pcm")

        return self

    @field_validator("prompt", mode="after")
    @classmethod
    def validate_prompt(cls, value: str) -> str:
        """Ensure that the prompt is not empty."""
        if not value.strip():
            raise ValueError("Prompt cannot be empty.")
        return value


# create/update (Crud)
class PostFileResponse(BaseModel):
    """Response model for `POST /v1/files/generated/:file_path`."""

    file_path: str = Field(
        description="The path to the file.",
        json_schema_extra={"example": "path/to/file.txt"},
    )
    message: str = Field(
        description="The message indicating the status of the operation.",
        json_schema_extra={"example": "New file generated and uploaded at path: path/to/file.txt"},
    )

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "value": {
                        "file_path": "path/to/file.txt",
                        "message": "New text file generated and uploaded at path: path/to/file.txt",
                    },
                },
                {
                    "value": {
                        "file_path": "path/to/image.png",
                        "message": "New image file generated and uploaded at path: path/to/image.png",
                    },
                },
                {
                    "value": {
                        "file_path": "path/to/speech.mp3",
                        "message": "New Text-to-Speech file generated and uploaded at path: path/to/speech.mp3",
                    },
                },
            ]
        }
    )
