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
