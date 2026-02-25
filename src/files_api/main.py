"""FastAPI application for managing files in an S3 bucket."""

import os
from textwrap import dedent
from typing import Union

import pydantic
from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.routing import APIRoute

from files_api.errors import (
    handle_broad_exceptions__middleware,
    handle_pydantic_validation_error,
)
from files_api.monitoring.logger import inject_lambda_context__middleware
from files_api.monitoring.metrics import start_metrics_context__middleware
from files_api.monitoring.tracer import start_xray_tracing__middleware
from files_api.routes import ROUTER
from files_api.settings import Settings

APP_DESCRIPTION = dedent(
    """\
    <a href="https://github.com/avr2002" target="_blank">\
        <img src="https://img.shields.io/badge/Maintained%20by-Amit%20Vikram%20Raj-F4BBFF?style=for-the-badge">\
    </a>
    <a href="https://github.com/avr2002/files-api" target="_blank">\
        <img src="https://img.shields.io/badge/github-repo-000000?style=for-the-badge&logo=github">\
    </a>
    <a href="https://mlops-club.org" target="_blank">\
        <img src="https://img.shields.io/badge/MLOps%20Club-05998B?style=for-the-badge">\
    </a>
    <br>
    """
)


def custom_generate_unique_id(route: APIRoute):
    """
    Generate prettier `operationId`s in the OpenAPI schema.

    These become the function names in generated client SDKs.
    """
    return f"{route.tags[0]}-{route.name}"


def create_app(settings: Union[Settings, None] = None) -> FastAPI:
    """Create a FastAPI application."""
    settings = settings or Settings()

    if os.getenv("COGNITO_ENABLED", "false").lower() == "false":
        swagger_ui_init_oauth = None
    else:
        swagger_ui_init_oauth = {
            "usePkceWithAuthorizationCodeGrant": True,
            "clientId": os.environ["COGNITO_USER_POOL_CLIENT_ID"],
            "additionalQueryStringParams": {"prompt": "login"},
        }

    app = FastAPI(
        title="Files API",
        summary="Store and Retrieve Files.",
        version="v1",  # a fancier version would read the semver from pkg metadata
        description=APP_DESCRIPTION,
        contact={
            "name": "Amit Vikram Raj",
            "url": "https://www.linkedin.com/in/avr27/",
            "email": "raj.amitvikram@gmail.com",
        },
        license_info={
            "name": "MIT License",
            "identifier": "MIT",
            "url": "https://github.com/avr2002/files-api/blob/main/LICENSE",
        },
        docs_url="/",  # its easier to find the docs when they live on the base url
        openapi_url="/openapi.json",
        redoc_url="/redoc",
        root_path="/prod",  # adding stage name to the root path
        generate_unique_id_function=custom_generate_unique_id,
        swagger_ui_oauth2_redirect_url="/docs/oauth2-redirect",  # default value
        swagger_ui_init_oauth=swagger_ui_init_oauth,
    )
    app.state.settings = settings
    app.include_router(ROUTER, prefix="/api")

    app.add_exception_handler(
        exc_class_or_status_code=RequestValidationError,
        handler=handle_pydantic_validation_error,
    )
    app.add_exception_handler(
        exc_class_or_status_code=pydantic.ValidationError,
        handler=handle_pydantic_validation_error,
    )
    # these middlewares get executed in reverse order that they are added(registered) to the app
    app.middleware("http")(
        handle_broad_exceptions__middleware
    )  # last middleware to be executed before the request is processed; first to execute after the request is processed
    app.middleware("http")(inject_lambda_context__middleware)
    app.middleware("http")(start_metrics_context__middleware)
    app.middleware("http")(
        start_xray_tracing__middleware
    )  # first middleware to get executed before the request is processed; last to execute after the request is processed
    return app


if __name__ == "__main__":
    import uvicorn

    app = create_app()
    uvicorn.run(app, host="0.0.0.0", port=8000)
