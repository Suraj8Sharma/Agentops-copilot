---
name: d30-trust-dashboard-metrics
description: Technical specification for Suraj's Day 30 tasks - Trust Dashboard metrics endpoint (GET /dashboard/metrics) aggregating latency, cost, accuracy, and fallback events for the Trust Dashboard per Manual Section 10, Section 14, and Gate 3.
---

# D30 Spec: Trust Dashboard Metrics Endpoint (`GET /dashboard/metrics`) & Week-5 PR Merge

**Task (Manual §14, D30, Suraj):** Trust Dashboard metrics endpoint; Week-5 PR merge.  
**Date:** Sat 26 Sep 2026 · **Owner:** Suraj (Backend Lead) · **Source:** Manual v2.0 (§6, §7 Group F, §7.2, §10, §14, §15.1, §17 Gate 3, §18 A6).  
**Depends on:** D21 (`llm_usage_logs` + rate-limit backoff handling), D25 (`eval_runs` + golden dataset ingestion), D26 (`planner_eval` and `router_eval` suites running in CI).  
**Consumer:** Ishani (Mobile Lead) wiring `TrustDashboardScreen` (`mobile/lib/features/trust_dashboard/trust_dashboard_screen.dart`).  
**Status:** Implemented & Verified (7/7 unit tests passing, 335/335 backend suite passing).  

---

## 1. Objective

Deliver the production-ready **Trust Dashboard Metrics Endpoint** (`GET /dashboard/metrics`) to power the mobile Trust Dashboard.

On Day 10, Ishani constructed the UI shell and mock visualizers in `trust_dashboard_screen.dart` with static 7-day metric series for **Latency**, **Cost**, and **Accuracy**, alongside a **Fallback Event** legend indicator. 

Section 14 of the Implementation Manual mandates that on Day 30, Suraj implements the backend aggregation endpoint that replaces this mock data with live operational data queried from the Group F service-role tables (`llm_usage_logs` and `eval_runs`), enforcing JWT session security and providing graceful zero-data fallbacks.

---

## 2. API Contract & Data Schema

### 2.1 Endpoint Specification

- **Method:** `GET`
- **Path:** `/dashboard/metrics`
- **Authentication:** Bearer JWT required (`CurrentUser` via `Depends(get_current_user)`)
- **Query Parameters:**
  - `days: int` (optional, default: `7`, range: `1` to `90`): Number of trailing calendar days to aggregate.

### 2.2 Response Schema

Matches the client-side `TrustDashboardMetrics` model in `mobile/lib/features/trust_dashboard/trust_dashboard_screen.dart`:

```json
{
  "latency": [
    {"label": "Mon", "value": 1.8},
    {"label": "Tue", "value": 2.4},
    {"label": "Wed", "value": 2.1},
    {"label": "Thu", "value": 3.0},
    {"label": "Fri", "value": 2.6},
    {"label": "Sat", "value": 2.2},
    {"label": "Sun", "value": 2.0}
  ],
  "cost": [
    {"label": "Mon", "value": 0.08},
    {"label": "Tue", "value": 0.12},
    {"label": "Wed", "value": 0.09},
    {"label": "Thu", "value": 0.15},
    {"label": "Fri", "value": 0.11},
    {"label": "Sat", "value": 0.07},
    {"label": "Sun", "value": 0.10}
  ],
  "accuracy": [
    {"label": "Mon", "value": 94.0},
    {"label": "Tue", "value": 96.0},
    {"label": "Wed", "value": 95.0},
    {"label": "Thu", "value": 97.0},
    {"label": "Fri", "value": 96.0},
    {"label": "Sat", "value": 98.0},
    {"label": "Sun", "value": 97.0}
  ],
  "summary": {
    "p95_latency": 2.2,
    "total_cost": 0.72,
    "avg_accuracy": 96.0,
    "fallback_events_count": 0
  },
  "fallback_events": 0
}
```

---

## 3. Metric Aggregation Details

### 3.1 Latency
- **Source:** `public.llm_usage_logs` (`latency_ms`, `created_at`).
- **Conversion:** `latency_ms / 1000.0` (in seconds).
- **Daily Value:** Daily p95 response time in seconds.
- **Summary:** Window-wide p95 response time in seconds.

### 3.2 Cost
- **Source:** `public.llm_usage_logs` (`provider`, `model`, `tokens_in`, `tokens_out`, `created_at`).
- **Formula:** `(tokens_in * input_rate + tokens_out * output_rate) / 1,000,000.0`.
- **Benchmark Pricing:**
  - Groq Llama 3.3 70B: \$0.59 / 1M in, \$0.79 / 1M out
  - Groq Llama 3.1 8B: \$0.05 / 1M in, \$0.08 / 1M out
  - Gemini 1.5/2.0 Flash: \$0.075 / 1M in, \$0.30 / 1M out
  - Gemini 1.5 Pro: \$1.25 / 1M in, \$5.00 / 1M out
- **Daily Value:** Total USD expenditure for the day.
- **Summary:** Total USD expenditure across the period.

### 3.3 Accuracy
- **Source:** `public.eval_runs` (`pass_count`, `fail_count`, `run_date`).
- **Formula:** `(pass_count / (pass_count + fail_count)) * 100.0`.
- **Daily Value:** Aggregate accuracy percentage across all eval suites run on that day. If no eval run occurred, propagates the most recent known score (or 0.0 if empty).
- **Summary:** Total passes divided by total evaluated cases in the period.

### 3.4 Fallback Events
- **Source:** `public.llm_usage_logs` (`rate_limit_hit == True`).
- **Surfacing:** Returned in `fallback_events` and `summary.fallback_events_count` to toggle the warning legend on the client.

---

## 4. Test Suite

Implemented in `backend/app/tests/test_dashboard.py`:
1. `test_get_dashboard_metrics_unauthenticated_returns_401`
2. `test_get_dashboard_metrics_empty_db_returns_safe_defaults`
3. `test_get_dashboard_metrics_aggregates_latency_p95`
4. `test_get_dashboard_metrics_calculates_cost_and_fallback`
5. `test_get_dashboard_metrics_calculates_accuracy_from_eval_runs`
6. `test_get_dashboard_metrics_custom_days_param`
7. `test_get_dashboard_metrics_handles_db_error_gracefully`
