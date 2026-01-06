"""
AWS Lambda handler using Mangum as an ASGI adapter for the FastAPI application.

Repository: https://github.com/jordaneremieff/mangum
"""

import json
import os
import urllib.request

from mangum import Mangum

from files_api.main import create_app

# Use the AWS-Parameters-and-Secrets-Lambda-Extension to retrieve secrets from Secrets Manager


# ref: https://docs.aws.amazon.com/systems-manager/latest/userguide/ps-integration-lambda-extensions.html
def get_secret_from_extension(secret_name: str) -> str:
    """Retrieves a secret value from the Secrets Manager extension."""
    # The extension runs on localhost port 2773 by default
    _extension_routing_port: str = os.environ["PARAMETERS_SECRETS_EXTENSION_HTTP_PORT"]

    # AWS_SESSION_TOKEN is required for authentication with the extension with the Secrets Manager
    _aws_session_auth_token: str = os.environ["AWS_SESSION_TOKEN"]

    endpoint = f"http://localhost:{_extension_routing_port}/secretsmanager/get?secretId={secret_name}"

    # Use the session token to authenticate with the extension
    req = urllib.request.Request(url=endpoint)
    req.add_header("X-Aws-Parameters-Secrets-Token", _aws_session_auth_token)

    # Request/Respone Syntax: https://docs.aws.amazon.com/secretsmanager/latest/apireference/API_GetSecretValue.html
    with urllib.request.urlopen(req) as response:
        secret_response = response.read().decode("utf-8")
        # The response is a JSON string containing the secret value
        secret_data = json.loads(secret_response)
        return secret_data["SecretString"]


# Cache the secret - only fetch once per cold start
_CACHED_OPENAI_API_KEY: str | None = None


# Create the FastAPI application
APP = create_app()


def handler(event, context):
    global _CACHED_OPENAI_API_KEY  # noqa: PLW0603
    # ^^^Using the global statement to update `_CACHED_OPENAI_API_KEY` is discouraged

    # Only fetch if not already cached
    if _CACHED_OPENAI_API_KEY is None:
        # Export the OpenAI API Key from secerets manager as an environment variable
        _CACHED_OPENAI_API_KEY = get_secret_from_extension(secret_name=os.environ["OPENAI_API_SECRET_NAME"])
        os.environ["OPENAI_API_KEY"] = _CACHED_OPENAI_API_KEY

    response = Mangum(APP)(event, context)
    return response
