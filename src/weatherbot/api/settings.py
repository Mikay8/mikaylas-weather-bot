"""Settings page endpoints: data coverage, source health, historical
backfill, and (when RAILWAY_TOKEN is configured) cron job status/trigger.
"""

import os
import time
from datetime import date, datetime, timedelta, timezone

import httpx
from fastapi import APIRouter, HTTPException
from sqlalchemy import text

from weatherbot.backtest.iem_forecast_backfill import run as run_iem_forecast_backfill
from weatherbot.backtest.iem_settlement_backfill import run as run_iem_settlement_backfill
from weatherbot.db import get_session
from weatherbot.ingest.nws_settlement import run as run_settlement_backfill

router = APIRouter(prefix="/api/settings")

RAILWAY_API_URL = "https://backboard.railway.com/graphql/v2"
RAILWAY_PROJECT_ID = "fc813a41-a996-4917-bfb9-40a4431813ba"
RAILWAY_ENVIRONMENT_ID = "00ae3a5a-1084-4336-9d0a-4a502333522f"

CRON_SERVICES = {
    "forecast": {
        "id": "9a0e699e-04c6-4c77-9a17-2205454e9382",
        "name": "forecast-cron",
        "schedule": "0 6,11,17,22 * * *",
        "schedule_label": "4x/day (6am, 11am, 5pm, 10pm UTC)",
    },
    "market": {
        "id": "2316dcb4-af92-4add-903f-9af233428e26",
        "name": "market-cron",
        "schedule": "0 * * * *",
        "schedule_label": "hourly",
    },
    "settlement": {
        "id": "cec2bf7d-05d8-46eb-b677-69da0f255fe2",
        "name": "settlement-cron",
        "schedule": "40 6 * * *",
        "schedule_label": "daily at 6:40am UTC (just after NWS publishes the CLI report)",
    },
}


@router.get("/data-coverage")
def data_coverage():
    session = get_session()
    try:
        def minmax(table: str, col: str) -> dict:
            row = session.execute(
                text(f"SELECT MIN({col}), MAX({col}), COUNT(*) FROM {table}")
            ).fetchone()
            return {"earliest": row[0], "latest": row[1], "row_count": row[2]}

        return {
            "forecasts": minmax("forecasts", "target_date"),
            "market_snapshots": minmax("market_snapshots", "timestamp"),
            "settlements": minmax("settlements", "date"),
        }
    finally:
        session.close()


@router.get("/source-health")
def source_health():
    results = {}

    contact = os.environ.get("NWS_USER_AGENT_CONTACT", "test@example.com")
    start = time.monotonic()
    try:
        resp = httpx.get(
            "https://api.weather.gov/points/40.7789,-73.9692",
            headers={"User-Agent": f"(mikaylas-weather-bot, {contact})"},
            timeout=10.0,
        )
        results["nws"] = {
            "reachable": resp.status_code == 200,
            "status_code": resp.status_code,
            "latency_ms": round((time.monotonic() - start) * 1000),
        }
    except httpx.HTTPError as e:
        results["nws"] = {"reachable": False, "error": str(e)}

    start = time.monotonic()
    try:
        resp = httpx.get(
            "https://external-api.kalshi.com/trade-api/v2/markets",
            params={"series_ticker": "KXHIGHNY", "limit": 1},
            timeout=10.0,
        )
        results["kalshi"] = {
            "reachable": resp.status_code == 200,
            "status_code": resp.status_code,
            "latency_ms": round((time.monotonic() - start) * 1000),
        }
    except httpx.HTTPError as e:
        results["kalshi"] = {"reachable": False, "error": str(e)}

    return results


@router.post("/backfill-settlements")
def backfill_settlements(limit: int = 14):
    """Backfill from NWS CLI reports. NWS only exposes ~6-7 days of CLI
    product history via this endpoint (confirmed against the live API,
    despite requesting more) — this is not a full historical backfill,
    just catches up on whatever NWS still has available."""
    try:
        run_settlement_backfill(limit=limit)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Backfill failed: {e}")

    session = get_session()
    try:
        row = session.execute(
            text("SELECT MIN(date), MAX(date), COUNT(*) FROM settlements")
        ).fetchone()
        return {"earliest": row[0], "latest": row[1], "row_count": row[2]}
    finally:
        session.close()


@router.post("/backfill-historical")
def backfill_historical(days: int = 365):
    """Backfill both settlements and next-day forecasts from IEM Mesonet
    (free, no key, back to 2000+) for the given number of days ending
    today. This is the real Phase 2 backtest data source — much deeper
    than the NWS CLI backfill above, which only covers the last week."""
    end = date.today()
    start = end - timedelta(days=days)

    try:
        run_iem_settlement_backfill(start, end)
        run_iem_forecast_backfill(start, end)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Historical backfill failed: {e}")

    session = get_session()
    try:
        settlements = session.execute(
            text("SELECT MIN(date), MAX(date), COUNT(*) FROM settlements")
        ).fetchone()
        forecasts = session.execute(
            text(
                "SELECT MIN(target_date), MAX(target_date), COUNT(*) FROM forecasts "
                "WHERE model_source = 'GFS_MOS'"
            )
        ).fetchone()
        return {
            "settlements": {"earliest": settlements[0], "latest": settlements[1], "row_count": settlements[2]},
            "forecasts": {"earliest": forecasts[0], "latest": forecasts[1], "row_count": forecasts[2]},
        }
    finally:
        session.close()


def _railway_token() -> str:
    token = os.environ.get("RAILWAY_TOKEN")
    if not token:
        raise HTTPException(
            status_code=501,
            detail="RAILWAY_TOKEN not configured — cron status/trigger unavailable",
        )
    return token


def _railway_graphql(query: str, variables: dict) -> dict:
    token = _railway_token()
    resp = httpx.post(
        RAILWAY_API_URL,
        json={"query": query, "variables": variables},
        headers={"Project-Access-Token": token},
        timeout=15.0,
    )
    resp.raise_for_status()
    body = resp.json()
    if "errors" in body:
        raise HTTPException(status_code=502, detail=f"Railway API error: {body['errors']}")
    return body["data"]


DEPLOYMENTS_QUERY = """
query($serviceId: String!, $environmentId: String!) {
  deployments(
    input: { serviceId: $serviceId, environmentId: $environmentId }
    first: 10
  ) {
    edges { node { id status meta createdAt updatedAt } }
  }
}
"""

DEPLOY_MUTATION = """
mutation($serviceId: String!, $environmentId: String!) {
  serviceInstanceDeployV2(serviceId: $serviceId, environmentId: $environmentId)
}
"""

# Redeploys (triggered by a git push, reason="deploy"/"redeploy") build a fresh
# image but don't represent the script actually executing on schedule — only
# reason="cron" (or none, on older deployments) reflects a real scheduled run.
_NON_CRON_REASONS = {"deploy", "redeploy"}


@router.get("/cron-status")
def cron_status():
    out = {}
    for key, svc in CRON_SERVICES.items():
        entry = {
            "name": svc["name"],
            "schedule": svc["schedule"],
            "schedule_label": svc["schedule_label"],
        }
        try:
            data = _railway_graphql(
                DEPLOYMENTS_QUERY,
                {"serviceId": svc["id"], "environmentId": RAILWAY_ENVIRONMENT_ID},
            )
            edges = data["deployments"]["edges"]
            run_node = next(
                (
                    e["node"]
                    for e in edges
                    if e["node"].get("meta", {}).get("reason") not in _NON_CRON_REASONS
                ),
                None,
            )
            if run_node:
                entry["last_run_status"] = run_node["status"]
                entry["last_run_at"] = run_node["createdAt"]
                skipped_reason = run_node.get("meta", {}).get("skippedReason")
                if skipped_reason:
                    entry["last_run_detail"] = skipped_reason
                config_errors = run_node.get("meta", {}).get("configErrors")
                if config_errors:
                    entry["last_run_detail"] = "; ".join(config_errors)
            else:
                entry["last_run_status"] = "NEVER_RUN"
                entry["last_run_at"] = None
        except HTTPException as e:
            entry["error"] = e.detail
        out[key] = entry
    return out


@router.post("/cron-trigger/{key}")
def cron_trigger(key: str):
    svc = CRON_SERVICES.get(key)
    if svc is None:
        raise HTTPException(status_code=404, detail=f"Unknown cron job: {key}")
    data = _railway_graphql(
        DEPLOY_MUTATION,
        {"serviceId": svc["id"], "environmentId": RAILWAY_ENVIRONMENT_ID},
    )
    return {"deployment_id": data["serviceInstanceDeployV2"], "triggered_at": datetime.now(timezone.utc)}
