"""Tracing module for AWS X-Ray SDK integration."""

import os
from contextlib import contextmanager
from typing import Any, Generator

from aws_xray_sdk.core import patch_all, xray_recorder
from aws_xray_sdk.core.models.facade_segment import FacadeSegment
from aws_xray_sdk.core.models.segment import Segment
from aws_xray_sdk.core.models.subsegment import Subsegment
from aws_xray_sdk.core.utils.stacktrace import get_stacktrace
from fastapi import Request, Response
from loguru import logger


def configure_tracing():
    """Configure AWS X-Ray SDK."""
    # Read about double patching here: https://docs.aws.amazon.com/xray/latest/devguide/xray-sdk-python-patching.html
    patch_all(double_patch=True)


async def start_xray_tracing__middleware(request: Request, call_next):
    """Middleware to add a top-level X-Ray segment around the request/response cycle."""
    with get_current_segment_or_create_if_not_exists("Files API") as segment:
        with (
            xray_recorder.in_subsegment("Handle Request") as subsegment,
            inject_trace_context_into_logger(segment=segment),
        ):
            response = await call_next(request)
            http_metadata: dict[str, str] = get_http_metadata(request, response)
            log_http_metadata_to_subsegment(http_metadata, subsegment)

            # If we're in AWS lambda, then the segment is a FacadeSegment which cannot be modified,
            # and indeed an AWS Lambda function is not an independent HTTP service so it would
            # not make sense to put the HTTP metadata on the root segment of a Lambda function.
            if not is_running_in_lambda():
                log_http_metadata_to_segment(http_metadata, segment)

            logger.debug("AWS X-Ray trace segment", raw_trace_segment=segment.to_dict())
            return response


@contextmanager
def get_current_segment_or_create_if_not_exists(
    segment_name: str,
) -> Generator[Segment, Any, None]:
    """Check if a segment is already active, and if so, yield it. Otherwise, create a new segment."""
    current_segment: Segment | FacadeSegment | None = xray_recorder.current_segment()
    if current_segment:
        yield current_segment
        return  # Exit early if a segment is already active

    with xray_recorder.in_segment(segment_name) as segment:
        yield segment


def is_running_in_lambda() -> bool:
    """Check if the code is running in an AWS Lambda environment."""
    return "AWS_LAMBDA_FUNCTION_NAME" in os.environ


@contextmanager
def inject_trace_context_into_logger(
    segment: Segment | FacadeSegment,
) -> Generator[None, Any, None]:
    """Add trace context to logs."""
    trace_ctx = {
        # You can name the keys whatever you want, until the trace IDs values present in the logs, X-Ray will automatically pick them up.
        "xray-trace-id": segment.trace_id,
        "xray-segment-id": segment.id,
        "xray-parent-id": segment.parent_id,
    }
    with logger.contextualize(tracing=trace_ctx):
        yield


def get_http_metadata(request: Request, response: Response) -> dict[str, str]:
    """Extract HTTP metadata from the request and response objects to log to X-Ray segments/subsegments.

    Only specific metadata can be put on a segment/subsegment.
        Ref: https://docs.aws.amazon.com/xray/latest/devguide/xray-api-segmentdocuments.html#api-segmentdocuments-http
    """
    http_metadata = {
        "method": request.method,
        "url": str(request.url),
        "user_agent": request.headers.get("user-agent"),
        "client_ip": request.client.host,
        "status": response.status_code,
        "content_length": response.headers.get("content-length"),
    }
    return http_metadata


def log_http_metadata_to_segment(http_metadata: dict, segment: Segment) -> None:
    """Log HTTP metadata to a segment."""
    for key, value in http_metadata.items():
        segment.put_http_meta(key, value)


def log_http_metadata_to_subsegment(http_metadata: dict, subsegment: Subsegment) -> None:
    """Log HTTP metadata to a subsegment."""
    for key, value in http_metadata.items():
        subsegment.put_http_meta(key, value)


def capture_traceback_in_xray_trace(exc: Exception) -> None:
    """Capture the exception traceback in the current X-Ray subsegment."""
    # The Facade Segment cannot be modified, so we cannot add the exception to it.
    # If we're not in AWS Lambda, then log the exception to the current segment.
    if not is_running_in_lambda():
        current_segment: Segment = xray_recorder.current_segment()
        current_segment.add_exception(exc, stack=get_stacktrace())

    # If we're in AWS Lambda, then log the exception to the current subsegment `Handle Request`.
    current_subsegment: Subsegment = xray_recorder.current_subsegment()
    current_subsegment.add_exception(exc, stack=get_stacktrace())


def get_trace_context(segment: Segment | None = None) -> dict[str, str]:
    current_segment: Segment = segment or xray_recorder.current_segment()
    return {
        "xray-trace-id": current_segment.trace_id,
        "xray-segment-id": current_segment.id,
        "xray-parent-id": current_segment.parent_id,
    }
