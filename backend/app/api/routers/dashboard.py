"""Trust Dashboard metrics router — D30.

Endpoints
---------
GET /dashboard/metrics
    Returns aggregated latency, cost, and accuracy time series and summary
    for the Trust Dashboard.
    Auth: JWT required.

Sources
-------
- llm_usage_logs: Group F service-role table, records every LLM call
  (latency_ms, tokens_in, tokens_out, provider, model, rate_limit_hit).
- eval_runs: Group F service-role table, records eval-suite runs
  (pass_count, fail_count, avg_latency_ms, run_date).
"""

from __future__ import annotations

import logging
import math
from datetime import datetime, timedelta, timezone
from typing import Annotated, List, Optional

from fastapi import APIRouter, Depends, Query, status
from pydantic import BaseModel, Field

from app.core.security import CurrentUser, get_current_user
from app.db.supabase_client import supabase_admin

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/dashboard", tags=["dashboard"])

# Benchmark token pricing per 1,000,000 tokens (USD)
_MODEL_RATES: dict[str, dict[str, float]] = {
    # Groq models
    "llama-3.3-70b-versatile": {"input": 0.59, "output": 0.79},
    "llama-3.1-70b-versatile": {"input": 0.59, "output": 0.79},
    "llama-3.1-8b-instant": {"input": 0.05, "output": 0.08},
    "mixtral-8x7b-32768": {"input": 0.24, "output": 0.24},
    # Gemini models
    "gemini-1.5-flash": {"input": 0.075, "output": 0.30},
    "gemini-2.0-flash": {"input": 0.075, "output": 0.30},
    "gemini-1.5-pro": {"input": 1.25, "output": 5.00},
}
_DEFAULT_RATES = {"input": 0.10, "output": 0.30}


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class DashboardMetricPoint(BaseModel):
    """A single data point in a metric time series."""

    label: str = Field(..., description="Day or category label, e.g. 'Mon', 'Tue'")
    value: float = Field(..., description="Metric value (seconds, USD, or percentage)")


class TrustDashboardSummary(BaseModel):
    """Aggregate summary statistics across the entire requested period."""

    p95_latency: float = Field(..., description="p95 response time in seconds")
    total_cost: float = Field(..., description="Total LLM spend in USD")
    avg_accuracy: float = Field(..., description="Average pass rate percentage (0-100)")
    fallback_events_count: int = Field(..., description="Count of rate-limit fallback events")


class TrustDashboardResponse(BaseModel):
    """Payload for GET /dashboard/metrics, consumed by Flutter TrustDashboardScreen."""

    latency: List[DashboardMetricPoint] = Field(
        ..., description="Latency series in seconds (p95 per day)"
    )
    cost: List[DashboardMetricPoint] = Field(
        ..., description="Cost series in USD (LLM spend per day)"
    )
    accuracy: List[DashboardMetricPoint] = Field(
        ..., description="Accuracy series in percentage (eval pass rate per day)"
    )
    summary: TrustDashboardSummary = Field(
        ..., description="Overall summary metrics across the requested window"
    )
    fallback_events: int = Field(..., description="Total fallback events count for the legend")


# ---------------------------------------------------------------------------
# Calculation Helpers
# ---------------------------------------------------------------------------


def _calc_p95(values: list[float]) -> float:
    """Calculate p95 value from a list of floats, matching the client-side math."""
    if not values:
        return 0.0
    sorted_vals = sorted(values)
    idx = min(len(sorted_vals) - 1, math.ceil(len(sorted_vals) * 0.95) - 1)
    return round(sorted_vals[idx], 2)


def _calc_cost(model: str, tokens_in: int, tokens_out: int) -> float:
    """Calculate estimated cost in USD based on token counts and model rates."""
    rates = _MODEL_RATES.get(model, _DEFAULT_RATES)
    cost = (tokens_in * rates["input"] + tokens_out * rates["output"]) / 1_000_000.0
    return cost


def _parse_date(date_str: str) -> Optional[datetime.date]:
    """Safely parse ISO timestamp into a date."""
    if not date_str:
        return None
    try:
        # Fast path: first 10 characters are YYYY-MM-DD
        dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
        return dt.astimezone(timezone.utc).date()
    except Exception:
        try:
            return datetime.strptime(date_str[:10], "%Y-%m-%d").date()
        except Exception:
            return None


# ---------------------------------------------------------------------------
# GET /dashboard/metrics
# ---------------------------------------------------------------------------


@router.get(
    "/metrics",
    response_model=TrustDashboardResponse,
    status_code=status.HTTP_200_OK,
    summary="Get Trust Dashboard metrics",
    description=(
        "Returns aggregated latency, cost, and accuracy time series for the Trust Dashboard. "
        "Aggregates data from llm_usage_logs and eval_runs. Requires JWT authentication."
    ),
)
def get_dashboard_metrics(
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    days: int = Query(7, ge=1, le=90, description="Number of past days to aggregate (default: 7)"),
) -> TrustDashboardResponse:
    """Aggregate trust metrics for the requested day window."""
    now = datetime.now(timezone.utc)
    start_date = (now - timedelta(days=days - 1)).date()
    cutoff_iso = datetime.combine(start_date, datetime.min.time(), tzinfo=timezone.utc).isoformat()

    # Pre-generate chronological date slots
    slot_dates = [start_date + timedelta(days=i) for i in range(days)]
    date_labels: dict[datetime.date, str] = {
        d: d.strftime("%a") if days <= 7 else d.strftime("%b %d") for d in slot_dates
    }

    # Buckets per day
    day_latencies: dict[datetime.date, list[float]] = {d: [] for d in slot_dates}
    day_costs: dict[datetime.date, float] = {d: 0.0 for d in slot_dates}
    day_eval_passes: dict[datetime.date, int] = {d: 0 for d in slot_dates}
    day_eval_fails: dict[datetime.date, int] = {d: 0 for d in slot_dates}

    all_latencies: list[float] = []
    total_cost: float = 0.0
    fallback_events_count: int = 0

    # 1. Query llm_usage_logs (latency, cost, rate_limit_hit)
    try:
        llm_cols = "provider, model, tokens_in, tokens_out, latency_ms, rate_limit_hit, created_at"
        llm_res = (
            supabase_admin.table("llm_usage_logs")
            .select(llm_cols)
            .gte("created_at", cutoff_iso)
            .order("created_at")
            .execute()
        )
        llm_rows = llm_res.data or []
    except Exception as exc:
        logger.error("Failed to query llm_usage_logs for dashboard metrics: %s", exc, exc_info=True)
        llm_rows = []

    for row in llm_rows:
        row_date = _parse_date(row.get("created_at", ""))
        lat_s = (row.get("latency_ms") or 0) / 1000.0
        all_latencies.append(lat_s)

        cost = _calc_cost(
            model=row.get("model") or "",
            tokens_in=row.get("tokens_in") or 0,
            tokens_out=row.get("tokens_out") or 0,
        )
        total_cost += cost

        if row.get("rate_limit_hit"):
            fallback_events_count += 1

        if row_date in day_latencies:
            day_latencies[row_date].append(lat_s)
            day_costs[row_date] += cost

    # 2. Query eval_runs (accuracy)
    try:
        eval_res = (
            supabase_admin.table("eval_runs")
            .select("pass_count, fail_count, avg_latency_ms, run_date")
            .gte("run_date", cutoff_iso)
            .order("run_date")
            .execute()
        )
        eval_rows = eval_res.data or []
    except Exception as exc:
        logger.error("Failed to query eval_runs for dashboard metrics: %s", exc, exc_info=True)
        eval_rows = []

    total_eval_passes = 0
    total_eval_fails = 0

    for row in eval_rows:
        row_date = _parse_date(row.get("run_date", ""))
        passes = row.get("pass_count") or 0
        fails = row.get("fail_count") or 0
        total_eval_passes += passes
        total_eval_fails += fails

        if row_date in day_eval_passes:
            day_eval_passes[row_date] += passes
            day_eval_fails[row_date] += fails

    # 3. Construct Metric Series
    latency_series: list[DashboardMetricPoint] = []
    cost_series: list[DashboardMetricPoint] = []
    accuracy_series: list[DashboardMetricPoint] = []

    last_known_accuracy = 0.0

    for d in slot_dates:
        lbl = date_labels[d]

        # Latency point: p95 for the day (or 0.0 if no calls)
        p95_day = _calc_p95(day_latencies[d])
        latency_series.append(DashboardMetricPoint(label=lbl, value=p95_day))

        # Cost point: total cost for the day in USD
        cost_series.append(DashboardMetricPoint(label=lbl, value=round(day_costs[d], 2)))

        # Accuracy point: pass rate for the day
        d_pass = day_eval_passes[d]
        d_fail = day_eval_fails[d]
        d_total = d_pass + d_fail
        if d_total > 0:
            d_acc = round((d_pass / d_total) * 100.0, 1)
            last_known_accuracy = d_acc
        else:
            # If no eval ran on this specific day, use last known or 0.0
            d_acc = last_known_accuracy
        accuracy_series.append(DashboardMetricPoint(label=lbl, value=d_acc))

    # 4. Construct Summary
    total_evals = total_eval_passes + total_eval_fails
    overall_accuracy = (
        round((total_eval_passes / total_evals) * 100.0, 1) if total_evals > 0 else 0.0
    )

    summary = TrustDashboardSummary(
        p95_latency=_calc_p95(all_latencies),
        total_cost=round(total_cost, 2),
        avg_accuracy=overall_accuracy,
        fallback_events_count=fallback_events_count,
    )

    return TrustDashboardResponse(
        latency=latency_series,
        cost=cost_series,
        accuracy=accuracy_series,
        summary=summary,
        fallback_events=fallback_events_count,
    )
