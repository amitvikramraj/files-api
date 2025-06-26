"""Settings for the Files API."""

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Settings for the Files API.

    Pydantic BaseSettings Docs: https://docs.pydantic.dev/latest/concepts/pydantic_settings
    FastAPI Guide to manage Settings: https://fastapi.tiangolo.com/advanced/settings/
    """

    s3_bucket_name: str = Field(...)

    model_config = SettingsConfigDict(case_sensitive=False)
