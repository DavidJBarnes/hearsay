"""Prometheus ``/metrics`` endpoint."""

from __future__ import annotations

from fastapi import APIRouter, Response

from hearsay_api.metrics import render_metrics

router = APIRouter()


@router.get("/metrics")
async def metrics() -> Response:
    """Render current metrics in Prometheus text format."""
    body, content_type = render_metrics()
    return Response(content=body, media_type=content_type)
