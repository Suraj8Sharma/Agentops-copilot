# D25 Spec: Eval Tables + Golden-Dataset Ingestion

**Task (Manual §14, D25, Suraj):** `eval_cases` / `eval_runs` tables; golden-dataset ingestion pipeline
**Date:** Mon 21 Sep 2026 · **Owner:** Suraj · **Source:** Manual v2.0 (§7 Group F, §7.2, §15.1, §18 A5)
**Unblocks:** Sanskriti's D25 task, Suraj's D26 eval harness, Gate 3 (Sat 26 Sep)

---

## 1. What we are building (plain language)

Sanskriti and Shivangi write test questions ("golden cases") for the LLM parts of the agent, in a text file. Today we build three things:

1. **`eval_runs`**: one row per exam sitting (date, which suite, passes, fails, average speed).
2. **`eval_cases`**: one row per test question, with its expected answer.
3. **A loader script**: reads `docs/eval/golden_dataset.jsonl`, checks every line, and puts the cases into `eval_cases`.

Nothing runs the agent today. D26 builds the harness that replays these cases.

---

## 2. Preconditions (verify before starting or handing to a coding agent)

This spec assumes D24 is complete. Confirm each:

- [ ] `supabase db push` works from your machine and every earlier migration in `backend/migrations/` is applied. Note the newest file's name; new files follow the same naming pattern.
- [ ] `backend/.env` has `SUPABASE_URL` and `SUPABASE_SERVICE_ROLE_KEY`. Nothing else is needed for this task.
- [ ] `docs/eval/golden_dataset.jsonl` is on `main`. Expected content: the 40 cases from D12 (15 planner/router, 15 risk-explanation, 10 OAuth/edge-case) plus banner cases (D21) and MCP-failure cases (D22). Open it and read the first few lines: confirm the key names and category spellings.
- [ ] `ci.yml` runs ruff + pytest on PRs, and the Supabase Python client is in `requirements.txt`.

If any box fails, fix that first.

---

## 3. Decisions locked for this spec

| # | Decision | Why |
|---|---|---|
| 1 | Golden cases are rows with `run_id IS NULL`. When D26 grades a run, it inserts **new** rows (copy of the case plus that run's `run_id`, `actual_output`, `pass`, `evaluated_at`). It never overwrites a golden row. | The regression test (§15.1) compares against the last frozen run, so per-case results of old runs must survive. |
| 2 | A case's identity is `(category, input_prompt)` among golden rows. No unique constraint is added; the loader compares in Python. | Keeps the schema exactly as the manual defines it. About 100 rows is trivial to diff. |
| 3 | All-or-nothing validation: one bad line means nothing is written. | A half-loaded dataset makes eval scores meaningless. |
| 4 | The loader never deletes. Cases in the DB that are not in the file are reported as "orphans". | Deleting on a typo'd edit would silently drop a test. |
| 5 | `--validate-only` needs no database and no secrets. The real load uses the service-role key and stays with Suraj / CI. | The service-role key bypasses RLS on every table. Teammates only need it to check a file, which validate-only covers. |
| 6 | Loader lives at `backend/app/eval/ingest_golden.py` (new folder). | §11 has no eval folder; D26's harness can sit next to it. Alternative: `backend/scripts/`. |

If D26 later chooses to overwrite golden rows in place instead of decision 1, the loader's lookup must change. Lock decision 1 today.

---

## 4. Step 1: Write the two migrations

Two new files in `backend/migrations/`, following the existing naming pattern. The `eval_runs` file must sort **before** the `eval_cases` file, because of the foreign key.

**File A: `eval_runs`**

```sql
create table eval_runs (
  id             uuid primary key default gen_random_uuid(),
  run_date       timestamptz default now(),
  suite_name     text check (suite_name in
                   ('planner_eval','router_eval','risk_explainer_eval','banner_model_eval')),
  pass_count     int,
  fail_count     int,
  avg_latency_ms int,
  notes          text
);

alter table eval_runs enable row level security;
-- No policies on purpose: service-role only (§7 Group F, A5).
```

**File B: `eval_cases`**

```sql
create table eval_cases (
  id              uuid primary key default gen_random_uuid(),
  category        text check (category in
                    ('planner','router','risk_explanation','banner','oauth_edge_case','mcp_failure')),
  input_prompt    text not null,
  expected_output jsonb,
  actual_output   jsonb,
  pass            boolean,
  run_id          uuid references eval_runs(id),
  evaluated_at    timestamptz
);

create index eval_cases_run_id_idx on eval_cases (run_id);

alter table eval_cases enable row level security;
-- No policies on purpose: service-role only.
```

Notes:
- `run_id` is nullable: golden rows are loaded before any run exists.
- The foreign key has no cascade (default). A run that has graded rows cannot be deleted by accident.
- No `pgcrypto` extension needed; `gen_random_uuid()` is built in.
- No RLS policies means the "one policy per command" syntax issue does not come up.

**Check:** compare both files line by line against the §7 Group F tables. `eval_runs` sorts first.

---

## 5. Step 2: Apply and verify structure

```powershell
supabase db push
```

Then in the Supabase SQL editor:

```sql
select table_name, column_name, data_type, is_nullable
from information_schema.columns
where table_name in ('eval_runs','eval_cases')
order by table_name, ordinal_position;

select tablename, rowsecurity from pg_tables
where tablename in ('eval_runs','eval_cases');

select count(*) from pg_policies
where tablename in ('eval_runs','eval_cases');
```

**Check:** columns match §7; `rowsecurity` is true for both; policy count is 0; `eval_cases.run_id` is nullable and `input_prompt` is not.

---

## 6. Step 3: Build the loader

**File:** `backend/app/eval/ingest_golden.py` (add `__init__.py` if the other `app` packages have one).

**Structure.** Only `load` touches the database, so everything else is testable without secrets:

```python
ALLOWED_CATEGORIES = ("planner", "router", "risk_explanation",
                      "banner", "oauth_edge_case", "mcp_failure")

validate_file(path) -> (cases, errors, warnings)      # pure: no DB, no env vars
plan_changes(cases, existing_rows) -> Plan            # pure: inserts / updates / unchanged / orphans
load(plan, client) -> Summary                         # the only function that writes
main(argv) -> int                                     # CLI, exit codes below
```

**Input format.** One JSON object per line. The manual's D5 format is `input / expected / category`. Confirm the real key names in Sanskriti's file and keep the mapping in one constant. Accept either name so the file never has to be rewritten:

| File key | Alias also accepted | DB column |
|---|---|---|
| `input` | `input_prompt` | `input_prompt` |
| `expected` | `expected_output` | `expected_output` |
| `category` | none | `category` |

**Validation rules.** Collect every problem, report each with its line number, do not stop at the first:

1. Line is valid JSON and a JSON object. Blank lines are skipped.
2. `category`, after trim + lowercase, exactly matches one of the six allowed values. No guessing or fuzzy mapping.
3. `input` is a non-empty string. Store it trimmed.
4. `expected` is present. Any JSON value is fine (object, array, string), since the column is jsonb.
5. No duplicate `(category, input)` inside the file; report both line numbers.
6. Unknown extra keys are a **warning**, not an error. They are not stored.
7. Open the file as `utf-8-sig` so a Windows BOM does not break line 1.

**Flow.**

1. Validate the whole file. Any error: print the report, exit 1, write nothing.
2. If `--validate-only`: print counts per category, exit 0. Stop here (no env vars read).
3. Create the client from `SUPABASE_URL` + `SUPABASE_SERVICE_ROLE_KEY`. Missing or failing: exit 2.
4. Fetch existing golden rows (`run_id IS NULL`): `id, category, input_prompt, expected_output`.
5. Diff by `(category, input_prompt)`:
   - not in DB: **insert** (batched)
   - in DB, `expected_output` differs: **update** that column
   - in DB, identical: **unchanged**
   - in DB but not in file: **orphan** (report only)
6. Print the summary, exit 0.

Compare `expected_output` as parsed JSON (Python equality), never as text. jsonb reorders keys, so a text comparison would report false updates on every run and break idempotency.

**CLI** (PowerShell, from `backend/` with the venv active):

```powershell
python -m app.eval.ingest_golden --validate-only
python -m app.eval.ingest_golden
python -m app.eval.ingest_golden --file ..\docs\eval\golden_dataset.jsonl
```

The default path resolves `docs/eval/golden_dataset.jsonl` from the repo root, not from the current directory.

**Exit codes:** `0` success · `1` validation errors · `2` config or DB error.

**Report format:**

```
File: docs/eval/golden_dataset.jsonl
Lines read: N | valid: N | errors: N | warnings: N
By category: planner N, router N, risk_explanation N, banner N, oauth_edge_case N, mcp_failure N
Load: inserted N | updated N | unchanged N | orphaned N
line 14: category 'oauth' is not one of: planner, router, risk_explanation, ...
```

**Security:** read secrets from the environment only. Never print the key or URL, never log request headers, never commit `.env`.

**Check:** run `--validate-only` on the real file. Either exit 0 with a category breakdown, or a line-numbered problem list to send to Sanskriti/Shivangi.

---

## 7. Step 4: Tests

**File:** `backend/app/tests/eval/test_eval_ingest.py` (Appendix B runs `pytest app/tests/eval`). All tests use `tmp_path` files and stub rows. No database, so they run in CI without secrets.

| Test | Proves |
|---|---|
| `test_ingest_valid_file_parses_all_cases` | Happy path, all six categories |
| `test_ingest_skips_blank_lines_and_handles_utf8_bom` | Windows-edited files load |
| `test_ingest_rejects_invalid_json_line` | Error carries the line number |
| `test_ingest_rejects_unknown_category_with_line_number` | Strict category check |
| `test_ingest_rejects_empty_input` | Rule 3 |
| `test_ingest_rejects_duplicate_case_in_file` | Rule 5, both line numbers reported |
| `test_ingest_accepts_column_name_aliases` | `input_prompt` / `expected_output` keys work |
| `test_ingest_warns_on_unknown_keys_without_failing` | Rule 6 |
| `test_ingest_any_invalid_line_means_nothing_written` | All-or-nothing (decision 3) |
| `test_plan_changes_second_run_is_all_unchanged` | Idempotent, including reordered JSON keys |
| `test_plan_changes_updates_expected_output_when_file_changes` | Update path |
| `test_plan_changes_reports_orphans_without_deleting` | Decision 4 |
| `test_validate_only_needs_no_env_vars` | Decision 5 (monkeypatch env empty) |

Also: when the Security/RLS suite is written, add both tables to the list checked by `test_rls_service_role_tables_not_exposed_to_client` (§15.4). Today's manual SQL check in Step 5 covers it until then.

**Check:** `ruff check .` and `pytest app/tests/eval -v` are green locally.

---

## 8. Step 5: First real load and verification

1. Run `python -m app.eval.ingest_golden`. Expect `inserted` = valid line count, others 0.
2. In SQL editor:

```sql
select category, count(*) from eval_cases
where run_id is null group by category order by category;
```

Counts match the loader's per-category report.

3. Run the loader again. Expect `inserted 0 | updated 0`.
4. RLS check. Run **after** the load; an empty table proves nothing:

```sql
begin;
set local role anon;
select count(*) from eval_cases;   -- expect 0 rows, or "permission denied"; never the real count
rollback;
```

**Check:** all four results as described.

---

## 9. Step 6: Docs and PR

- One paragraph of docs the same day (§16.3). Put it in `backend/app/eval/README.md` or the module docstring. It must cover: file location and format, the two commands (`--validate-only` and the real load), what "orphaned" means, and that golden rows are `run_id IS NULL`.
- Branch: `feat/d25-eval-tables-ingest`. Two PRs is fine: (1) migrations, (2) loader + tests. Sanskriti only needs the loader, so merge that first if it is ready earlier.
- Branch protection needs one review and green CI (ruff + pytest).

---

## 10. Done when

- [ ] Both migrations merged and applied; `eval_runs` sorts before `eval_cases`
- [ ] Columns match §7; RLS on with zero policies; `anon` cannot read rows after load
- [ ] `--validate-only` on the real file exits 0, or its problem list has been sent to the authors
- [ ] `eval_cases` golden row count equals valid lines in the file; per-category counts match
- [ ] Second load inserts 0 and updates 0
- [ ] Tests green locally and in CI
- [ ] Docs paragraph written; PR reviewed and merged

Definition of Done items that do not apply today (§16.3): fail-closed verification and `execution_logs` logging. Neither the risk path nor the agent loop is touched.

Contributes 2 of the 5 service-role-only tables counted by A5.

---

## 11. Handoff

**Sanskriti (D25):** runs `--validate-only` (no secrets needed) or receives Suraj's load report, and logs every line-level problem. Format fixes happen in the file; the loader stays strict. Shivangi can run the same command on her cases.

**D26 (harness):** reads golden rows (`run_id IS NULL`), creates one `eval_runs` row per suite, inserts graded copies with `run_id`, `actual_output`, `pass`, `evaluated_at`, then writes pass/fail counts and average latency to the run row. Category to suite mapping:

| Category | Suite (`suite_name`) |
|---|---|
| `planner` | `planner_eval` |
| `router` | `router_eval` |
| `risk_explanation` | `risk_explainer_eval` |
| `banner` | `banner_model_eval` |
| `oauth_edge_case`, `mcp_failure` | none defined (see below) |

Optional for D26: add `--validate-only` to `ci.yml` so a malformed golden file cannot merge.

`pass` is a Python keyword. In `db/models.py` or Pydantic models, name the field `passed` and map it to the column `pass`.

---

## 12. Open questions

1. **Six categories, four suites.** The manual gives `eval_cases.category` six values but `eval_runs.suite_name` only four. Decide on D26 which suite (if any) runs `oauth_edge_case` and `mcp_failure`; they may belong to the OAuth and MCP test suites rather than an LLM eval suite. The loader does not care either way.
2. **Actual key names in the golden file.** Section 6 assumes the D5 wording (`input / expected / category`). Confirm against Sanskriti's file before finalising the mapping constant.

---

## 13. Manual cross-reference and deviations

| Spec item | Manual reference |
|---|---|
| Task assignment | §14, D25 |
| `eval_runs` and `eval_cases` columns | §7 Group F |
| RLS on, no client policy | §7 Group F; §18 A5 |
| Index on `eval_cases.run_id` | §7.2 |
| File path and owners | §3; Appendix D (`docs/eval/golden_dataset.jsonl`) |
| Case format `input / expected / category` | §14, D5 |
| Eval loop and frozen-run regression | §15.1 |
| Named test style; `pytest app/tests/eval` | §15; Appendix B |

**Additions the manual does not specify** (review these when validating against the source):

1. `CHECK` constraints on `category` and `suite_name`.
2. Foreign key on `run_id` with no cascade.
3. Convention that golden rows have `run_id IS NULL` and graded results are new rows.
4. Loader location `backend/app/eval/` (§11 has no eval folder).
5. `--validate-only` mode, orphan reporting, and all-or-nothing validation.