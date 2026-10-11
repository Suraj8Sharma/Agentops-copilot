# Eval Golden Dataset Loader

This package contains the `ingest_golden.py` script to load eval cases from `docs/eval/golden_dataset.jsonl` into the `eval_cases` database table. The input file contains one JSON object per line with the format: `input` (or `input_prompt`), `expected` (or `expected_output`), and `category` (planner, router, risk_explanation, banner, oauth_edge_case, mcp_failure).

To run without applying changes and without needing database secrets, use `python -m app.eval.ingest_golden --validate-only`. To perform the real load, ensure `SUPABASE_URL` and `SUPABASE_SERVICE_ROLE_KEY` are set in your environment and run `python -m app.eval.ingest_golden`. The loader will insert new cases, update the expected output for existing cases if modified, leave unchanged cases alone, and report any cases in the DB but missing from the file as "orphaned". Golden rows are distinguished in the database by having `run_id IS NULL`.

## LLM Eval Suite Runner

The evaluation suite evaluates the Router and Planner components against Groq LLM responses. You can run the entire suite using `python -m app.eval.runner --suite all`. You can also target a specific suite with `--suite planner` or `--suite router`. To run a fast validation on a small subset of IDs, use the `--smoke` flag. In CI environments, run `python -m app.eval.runner --check-results` to verify that the latest run meets the expected thresholds without making new LLM calls.

**Groq Free Tier / Split Run Strategy:**
Due to Groq's free tier limits (30 RPM, 8000 TPM), the runner includes a built-in 5.0s pause between calls. However, running all 40 cases sequentially may still exhaust the Tokens Per Minute limit. If you encounter a 429 error, use the **20+20 split run strategy**:
1. Run the planner suite: `python -m app.eval.runner --suite planner`
2. Wait 2-3 minutes for the token quota to reset.
3. Run the router suite: `python -m app.eval.runner --suite router`

Because the runner merges results into `last_run.json` instead of overwriting it, your split runs will combine into a complete test run that can then be validated with `--check-results`.
