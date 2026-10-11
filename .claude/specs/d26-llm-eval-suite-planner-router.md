---
name: d26-llm-eval-suite-planner-router
description: Validated spec for the LLM eval harness (planner + router) - local live runs, free CI checks.
---

# D26: LLM Eval Suite v1 - Planner + Router

## 1. Metadata
- **Project**: AgentOps Copilot
- **Plan reference**: D26 (Suraj), depends on D25
- **Status**: Validated v2 (replaces Draft)
- **Run model**: live evals run **locally before push**; CI runs only free checks (see section 7)

## 2. Objective
Build the eval harness that replays the golden dataset (`planner` and `router` categories) against the planner and router, grades each case, and writes results to `eval_cases` and `eval_runs`. The pass rates are the evidence for Acceptance A1 and feed the Trust Dashboard accuracy panel.

## 3. Prerequisites (check before coding)
1. D25 is merged: `eval_cases` and `eval_runs` exist, and `python -m app.eval.ingest_golden` works.
2. `select category, count(*) from eval_cases where run_id is null group by 1` returns `planner 20` and `router 20`.
3. Ingest is idempotent on `expected_output.meta.id` (re-running does not create duplicates).
4. **Schema check**: confirm the real column names in your migration. This spec uses the manual's names: `eval_runs(run_date, suite_name, pass_count, fail_count, avg_latency_ms, notes)`. The old draft used `average_latency_ms`, `started_at`, `completed_at`, which are not in the manual. If you want them, add a migration; otherwise use `run_date` and drop them.

## 4. Data contract

### 4.1 Golden rows
Golden rows have `run_id IS NULL` and are read-only. Graded rows are new rows copied from the golden row with `run_id` set. The case id lives in `expected_output.meta.id` and is carried into the graded copy.

### 4.2 Targets under test
| Category | Entry point | Input | Output (parsed JSON) |
|---|---|---|---|
| planner | `run_planner(input_prompt, now)` | prompt plus `meta.now` (ISO, +05:30) injected into the prompt | `{steps[], unsupported?, reason?, needs_clarification?, missing?}` |
| router | `run_router(input_prompt)` | prompt | `{intent, mcp_servers[], needs_clarification, confidence}` |

Both run at **temperature 0**. Placeholder syntax in plans is `{{step_N.<path>}}` and must be stated in the planner prompt. Router intent is one of 11 labels: `calendar_read`, `calendar_write`, `email_read`, `email_write`, `github_read`, `github_write`, `slack_read`, `slack_write`, `multi_tool`, `ambiguous`, `out_of_scope`. The planner emits generic tool names (for example `slack.post_message`); risk-tag derives the specific `action_type` later.

## 5. Grading rules (pure functions in `backend/app/eval/scorers.py`)

### 5.1 Planner
A case passes only if **all** checks pass:
1. **Valid shape**: output parses and each step has `tool_name`, `mcp_server`, `input_params`; `tool_name` is in the known tool list; `mcp_server` is one of calendar/gmail/github/slack.
2. **Step count**: `len(steps)` is within `step_count_range`.
3. **Order and servers**: expected steps appear as an **ordered subsequence** of the actual steps (match on `tool_name` + `mcp_server`). Any extra steps must be `calendar.list_events` only (optional conflict check).
4. **Params**: for each matched step, every key in expected `input_params` must match exactly, except:
   - keys in `meta.free_text_fields`: only check non-empty string;
   - values containing `{{step_N...}}`: check a placeholder exists and N is an **earlier** step index; do not match the path after it.
5. **Forbidden params**: keys in `forbidden_params` must be absent from the step (also blocks `skip_approval`-style fields).
6. **Empty-plan cases**: if expected has `unsupported: true`, actual must have `steps == []` and `unsupported: true`. If expected has `needs_clarification: true`, actual must have `steps == []`, `needs_clarification: true`, and `missing` containing the expected keys.

**A1 metric** (valid-plan rate) = fraction passing check 1 alone. **Case pass rate** = fraction passing all checks. Report both.

### 5.2 Router
A case passes if: `intent` equals expected (exact), `set(mcp_servers)` equals expected set, and `needs_clarification` equals expected. Judge on overall accuracy, not per class (classes are small).

### 5.3 Confidence gating (not graded from the dataset)
The dataset has no confidence values. `test_router_confidence_threshold_gating` is a plain unit test with synthetic confidences: below the threshold (**placeholder 0.7**, tune after first run) the router result must not proceed to planning. Also assert RT-17 and RT-18 return `needs_clarification: true`.

## 6. Runner (`backend/app/eval/runner.py`)

### 6.1 CLI
`python -m app.eval.runner [--suite planner|router|all] [--smoke] [--no-cache] [--check-results]`
- `--smoke`: fixed subset of 6-8 case ids (listed in `docs/eval/smoke_ids.txt`), mixing both categories.
- `--check-results`: no LLM and no DB; validates `docs/eval/last_run.json` (section 7).

### 6.2 Flow (per suite, sequential)
1. Insert one `eval_runs` row (`suite_name` = `planner_eval` or `router_eval`).
2. Fetch golden rows for that category (`run_id IS NULL`, filtered by `category`).
3. For each case, with a **1-2 s pause** between live calls and exponential backoff on 429 (max 3 attempts):
   - look up the **cache** (key = sha256 of `model | prompt_version | temperature | case_id | input_prompt`); on a hit, skip the LLM;
   - otherwise call the target; latency = wall-clock of that single target call (cache hits record 0 and are excluded from the average);
   - grade with the scorers and insert a graded copy into `eval_cases`.
4. Update the `eval_runs` row: `pass_count`, `fail_count`, `avg_latency_ms`, and `notes` (JSON with `prompt_version`, `models_used`, git commit, cache-hit count).

### 6.3 Error handling
- **Provider errors (429, 5xx, timeout after retries)**: the case is **not run**. Set `pass = NULL`, `actual_output = {"error": ..., "type": "not_run"}`. Not-run cases are excluded from accuracy and flagged in `notes`; a run with any not-run cases is marked **incomplete** and does not update `last_run.json`.
- **Parse or validation failure of the model's output**: this is a real failure, `pass = FALSE`.
- **Fallback during eval**: Groq 429 falls back to Gemini only if `--allow-fallback` is set; the model used is recorded per case in `notes`. Default is **off**, so you grade the production primary model and do not burn Gemini quota.
- **Supabase write failure**: abort the run, exit code 2. Partial results are not trusted.
- **Quota guard**: after 3 consecutive 429s, stop the suite and mark the run incomplete.

## 7. Local-run and CI model

### 7.1 Local (live)
Run before every push that touches `agents/`, `llm/`, or prompt files: `python -m app.eval.runner --suite all` (cache on). Write `docs/eval/last_run.json` **only for complete runs**:
```json
{"date": "...", "commit": "<git sha>", "prompt_version": "...", "planner": {"valid_plan_rate": 0.0, "case_pass_rate": 0.0, "passed_ids": []}, "router": {"accuracy": 0.0, "passed_ids": []}}
```
Commit it with the push.

### 7.2 CI (`.github/workflows/ci.yml`, zero LLM calls, no service-role key)
1. `python -m app.eval.ingest_golden --validate-only` (must work offline; parses the JSONL only).
2. `pytest app/tests/eval/test_scorers.py` and the mocked tests (429 fallback, confidence gating).
3. `python -m app.eval.runner --check-results`: fails if `last_run.json` is missing, malformed, its `prompt_version` does not match the current one, or it fails the thresholds below.

This deviates from Section 12 of the manual (smoke eval on every PR). Record it in the D26 diary entry and the final report as a free-tier decision.

## 8. Thresholds (resolved)
| Metric | Gate | Note |
|---|---|---|
| Planner valid-plan rate (A1) | >= 90% | Matches the acceptance criterion |
| Planner case pass rate | report only until first real run | Then set a gate |
| Router accuracy | >= 85% | **Placeholder**, revisit after first run |
| Regression | no case in the last frozen run's `passed_ids` may now fail | Implements `test_eval_suite_regression_no_new_failures_vs_last_frozen_run`; the frozen run is the last committed `last_run.json` on `main` |

100% is not required: LLM output varies even at temperature 0 across provider updates.

## 9. Required tests (the six from the manual, plus scorers)
`test_planner_eval.py`: valid plan JSON, step-count range, correct MCP server per step. `test_router_eval.py`: intent accuracy, confidence gating (synthetic), Groq-429-to-Gemini fallback (mocked client; asserts Gemini called, answer returned, `llm_usage_logs` row with `rate_limit_hit = true`). `test_scorers.py`: hand-made good and bad outputs per rule in section 5.

## 10. Database isolation (resolved)
One Supabase project, no per-run DB. Golden rows are never modified. Graded rows are isolated by `run_id`. Live runs are local and sequential, so concurrent-run conflicts do not arise. Do not put the service-role key in CI.

## 11. Out of scope
`risk_explanation`, `banner_model_eval`, `oauth_edge_case`, `mcp_failure` suites; changing planner or router prompts (D26 only measures them); the real approval-gate bypass test (D31).

## 12. Done when (Section 16.3)
Reviewed PR merged; scorer unit tests and mocked tests green in CI; one complete local run written to `eval_runs` and `last_run.json`; LLM calls logged to `llm_usage_logs`; a paragraph in the README on running `pytest app/tests/eval -v` and the runner commands.