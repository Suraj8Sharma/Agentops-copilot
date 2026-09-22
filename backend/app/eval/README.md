# Eval Golden Dataset Loader

This package contains the `ingest_golden.py` script to load eval cases from `docs/eval/golden_dataset.jsonl` into the `eval_cases` database table. The input file contains one JSON object per line with the format: `input` (or `input_prompt`), `expected` (or `expected_output`), and `category` (planner, router, risk_explanation, banner, oauth_edge_case, mcp_failure).

To run without applying changes and without needing database secrets, use `python -m app.eval.ingest_golden --validate-only`. To perform the real load, ensure `SUPABASE_URL` and `SUPABASE_SERVICE_ROLE_KEY` are set in your environment and run `python -m app.eval.ingest_golden`. The loader will insert new cases, update the expected output for existing cases if modified, leave unchanged cases alone, and report any cases in the DB but missing from the file as "orphaned". Golden rows are distinguished in the database by having `run_id IS NULL`.
