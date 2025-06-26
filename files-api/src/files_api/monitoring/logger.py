import json
import os
import sys
import traceback
from uuid import uuid4

import loguru
from fastapi import Request, Response
from loguru import logger


def configure_logger():
    logger.remove()  # remove the default logger
    logger.add(
        sink=sys.stdout,
        diagnose=False,
        format="<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | <bold><white>{message}</white></bold> | <dim>{extra}</dim> {stacktrace}",
        filter=process_log_record,
    )


def process_log_record(record: "loguru.Record") -> "loguru.Record":
    r"""Inject transformed metadata into each log record before they are passed to the formatter.

    For instance,

    1. Serialize the "extra" field to JSON so that renders nicely in CloudWatch logs.
    2. For error logs, add a traceback with \r instead of \n so that CloudWatch does not
       split the traceback into multiple log events.
    """
    extra = record["extra"]

    # serialize "extra" field to JSON
    if extra:
        record["extra"] = json.dumps(extra, default=str)

    # add stacktrace to log record
    record["stacktrace"] = ""
    if record["exception"]:
        err = record["exception"]
        stacktrace = get_formatted_stacktrace(err, replace_newline_character_with_carriage_return=True)
        record["stacktrace"] = stacktrace

    return record


def get_formatted_stacktrace(loguru_record_exception, replace_newline_character_with_carriage_return: bool) -> str:
    """Get the formatted stacktrace for the current exception."""
    exc_type, exc_value, exc_traceback = loguru_record_exception
    stacktrace_: list[str] = traceback.format_exception(exc_type, exc_value, exc_traceback)
    stacktrace: str = "".join(stacktrace_)
    if replace_newline_character_with_carriage_return:
        stacktrace = stacktrace.replace("\n", "\r")
    return stacktrace


def log_request_info(request: Request):
    """Log the request info."""
    request_info = {
        "method": request.method,
        "path": request.url.path,
        "query_params": dict(request.query_params.items()),
        "path_params": dict(request.path_params.items()),
        "headers": dict(request.headers.items()),  # note: logging headers can leak secrets
        "base_url": str(request.base_url),
        "url": str(request.url),
        "client": str(request.client),
        "server": str(request.scope.get("server", "unknown")),
        "cookies": dict(request.cookies.items()),  # note: logging cookies can leak secrets
    }
    logger.debug("Request received", http_request=request_info)


def log_response_info(response: Response):
    """Log the response info."""
    response_info = {
        "status_code": response.status_code,
        "headers": dict(response.headers.items()),
    }
    logger.debug("Response sent", http_response=response_info)


async def inject_lambda_context__middleware(request: Request, call_next):
    """Middleware to add Lambda context to FastAPI request scope."""
    try:
        # Get the Lambda context from the incoming request headers
        context = request.scope["aws.context"]
        # https://docs.aws.amazon.com/lambda/latest/dg/configuration-envvars.html
        lambda_context = {
            "function_name": os.environ["AWS_LAMBDA_FUNCTION_NAME"],  # context.function_name,
            "function_arn": context.invoked_function_arn,
            "function_memory_size": os.environ["AWS_LAMBDA_FUNCTION_MEMORY_SIZE"],  # context.memory_limit_in_mb,
            "function_request_id": context.aws_request_id,
            "xray_trace_id": os.environ["_X_AMZN_TRACE_ID"].split(";")[0].strip("Root="),
        }
    except KeyError:
        # when running locally, set mocked values as context
        lambda_context = {
            "function_name": "n/a",
            "function_arn": "n/a",
            "function_memory_size": "n/a",
            "function_request_id": str(uuid4()),
        }

    with logger.contextualize(aws_lambda=lambda_context):
        response = await call_next(request)

    response.headers["X-Request-ID"] = lambda_context["function_request_id"]
    return response
