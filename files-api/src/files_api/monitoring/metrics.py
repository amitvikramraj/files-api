from contextvars import ContextVar

from aws_embedded_metrics import metric_scope
from aws_embedded_metrics.logger.metrics_logger import MetricsLogger
from fastapi import Request, Response

from files_api.monitoring.tracer import get_trace_context

metrics_ctx: ContextVar[MetricsLogger | None] = ContextVar("metrics_ctx", default=None)
"""Global, thread-safe context variable to store the MetricsLogger instance."""


async def start_metrics_context__middleware(request: Request, call_next):
    @metric_scope
    async def _start_metrics_context(metrics: MetricsLogger):
        # remove the `aws_embedded_metrics` library's default dimensions
        metrics.reset_dimensions(use_default=False)
        metrics.set_dimensions()
        metrics.set_property("tracing", value=get_trace_context())

        # Add the metrics logger to our custom context variable to
        metrics_ctx.set(metrics)

        response: Response = await call_next(request)
        return response

    return await _start_metrics_context()
