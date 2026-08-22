"""Persists outbound API request/response pairs to `api_call_logs` so the
Settings page can show the last 24h of traffic to NWS/IEM/ECMWF/Kalshi.

Hooked into each module's httpx.Client via event_hooks (see logged_client())
rather than wrapping every call site individually — request/response bodies
are read from the same event hooks httpx already offers for this purpose, so
existing call sites don't need to change beyond how they construct the client.
"""

import json
from datetime import datetime, timezone

import httpx
from sqlalchemy import text

from weatherbot.db import get_session

MAX_BODY_CHARS = 4000  # truncate large payloads (e.g. full gridpoint forecasts) before storing


def _truncate(body: bytes | str | None) -> str | None:
    if body is None:
        return None
    text_body = body.decode("utf-8", errors="replace") if isinstance(body, bytes) else body
    if len(text_body) > MAX_BODY_CHARS:
        return text_body[:MAX_BODY_CHARS] + "... [truncated]"
    return text_body


def _log_request(request: httpx.Request) -> None:
    request.extensions["log_start"] = datetime.now(timezone.utc)


def _write_log(source: str, request: httpx.Request, response: httpx.Response | None, error: str | None) -> None:
    start = request.extensions.get("log_start")
    latency_ms = int((datetime.now(timezone.utc) - start).total_seconds() * 1000) if start else None
    session = get_session()
    try:
        session.execute(
            text(
                """
                INSERT INTO api_call_logs
                    (source, method, url, request_body, status_code, response_body, error, latency_ms)
                VALUES
                    (:source, :method, :url, :request_body, :status_code, :response_body, :error, :latency_ms)
                """
            ),
            {
                "source": source,
                "method": request.method,
                "url": str(request.url),
                "request_body": _truncate(request.content) if request.content else None,
                "status_code": response.status_code if response is not None else None,
                "response_body": _truncate(response.text) if response is not None else None,
                "error": error,
                "latency_ms": latency_ms,
            },
        )
        session.execute(
            text("DELETE FROM api_call_logs WHERE created_at < now() - interval '24 hours'")
        )
        session.commit()
    except Exception:
        session.rollback()
    finally:
        session.close()


def make_logged_hooks(source: str) -> dict[str, list]:
    """event_hooks for httpx.Client(...) that log every request/response for `source`."""

    def on_response(response: httpx.Response) -> None:
        response.read()  # event hooks run before the caller can access .text; force the body now
        _write_log(source, response.request, response, error=None)

    return {"request": [_log_request], "response": [on_response]}
