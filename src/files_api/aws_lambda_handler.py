"""
AWS Lambda handler using Mangum as an ASGI adapter for the FastAPI application.

Repository: https://github.com/jordaneremieff/mangum
"""

import os

from mangum import Mangum

from files_api.main import create_app
from files_api.utils import get_parameter_from_extension

# from files_api.utils import get_secret_from_extension

# Cache the secret - only fetch once per cold start
_CACHED_OPENAI_API_KEY: str | None = None

# Create the FastAPI application
APP = create_app()


def handler(event, context):
    global _CACHED_OPENAI_API_KEY  # noqa: PLW0603
    # ^^^Using the global statement to update `_CACHED_OPENAI_API_KEY` is discouraged

    # Only fetch if not already cached
    if _CACHED_OPENAI_API_KEY is None or os.getenv("OPENAI_API_KEY") is None:
        # Export the OpenAI API Key from secerets manager as an environment variable
        # _CACHED_OPENAI_API_KEY = get_secret_from_extension(secret_name=os.environ["OPENAI_API_SECRET_NAME"])

        # Export the OpenAI API Key from SSM Parameter Store as an environment variable
        _CACHED_OPENAI_API_KEY = get_parameter_from_extension(
            name=os.environ["OPENAI_API_SSM_PARAMETER_NAME"],
            decrypt=True,
        )
        os.environ["OPENAI_API_KEY"] = _CACHED_OPENAI_API_KEY

    response = Mangum(APP)(event, context)
    return response
