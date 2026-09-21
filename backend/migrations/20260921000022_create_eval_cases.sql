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
