"""
D26 Eval Runner CLI.

Usage (from backend/ with venv active):
  python -m app.eval.runner [--suite planner|router|all] [--smoke]
                            [--no-cache] [--check-results] [--allow-fallback]

Options:
  --suite           Which suite to run: planner, router, or all (default: all)
  --smoke           Run only the fixed smoke subset (ids in docs/eval/smoke_ids.txt)
  --no-cache        Disable response cache (always hits the LLM)
  --check-results   No LLM, no DB. Validate docs/eval/last_run.json against thresholds.
  --allow-fallback  On Groq 429, fall back to Gemini (default: off)

Exit codes:
  0  success / all thresholds met
  1  thresholds not met or incomplete run
  2  DB or config error
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import logging
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parents[3]  # agentops/
LAST_RUN_PATH = REPO_ROOT / "docs" / "eval" / "last_run.json"
SMOKE_IDS_PATH = REPO_ROOT / "docs" / "eval" / "smoke_ids.txt"
CACHE_PATH = REPO_ROOT / "docs" / "eval" / ".eval_cache.json"

PLANNER_VALID_PLAN_THRESHOLD = 0.90  # A1 ≥ 90 %
ROUTER_ACCURACY_THRESHOLD = 0.85  # ≥ 85 %

INTER_CALL_PAUSE = (
    5.0  # seconds between live LLM calls (12 RPM — safe under 30 RPM + 8k TPM free tier)
)
MAX_CONSECUTIVE_429 = 3  # abort suite after this many back-to-back 429s

# ---------------------------------------------------------------------------
# Cache helpers
# ---------------------------------------------------------------------------


def _cache_key(
    model: str,
    prompt_version: str,
    temperature: float,
    case_id: str,
    input_prompt: str,
) -> str:
    raw = f"{model}|{prompt_version}|{temperature}|{case_id}|{input_prompt}"
    return hashlib.sha256(raw.encode()).hexdigest()


def _load_cache() -> dict[str, Any]:
    if CACHE_PATH.exists():
        try:
            return json.loads(CACHE_PATH.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def _save_cache(cache: dict[str, Any]) -> None:
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    CACHE_PATH.write_text(json.dumps(cache, indent=2), encoding="utf-8")


# ---------------------------------------------------------------------------
# Git helpers
# ---------------------------------------------------------------------------


def _git_commit() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"], cwd=REPO_ROOT, text=True
        ).strip()
    except Exception:
        return "unknown"


# ---------------------------------------------------------------------------
# DB helpers (Supabase)
# ---------------------------------------------------------------------------


def _get_supabase():
    from app.db.supabase_client import supabase_admin

    return supabase_admin


def _fetch_golden_rows(category: str) -> list[dict]:
    client = _get_supabase()
    res = (
        client.table("eval_cases")
        .select("id, category, input_prompt, expected_output")
        .is_("run_id", "null")
        .eq("category", category)
        .execute()
    )
    return res.data or []


def _insert_eval_run(suite_name: str) -> str:
    client = _get_supabase()
    res = client.table("eval_runs").insert({"suite_name": suite_name}).execute()
    return res.data[0]["id"]


def _insert_graded_case(
    golden_row: dict, run_id: str, actual_output: dict, passed: bool | None, latency_ms: int
) -> None:
    client = _get_supabase()
    row = {
        "category": golden_row["category"],
        "input_prompt": golden_row["input_prompt"],
        "expected_output": golden_row["expected_output"],
        "actual_output": actual_output,
        "pass": passed,
        "run_id": run_id,
        "evaluated_at": datetime.now(timezone.utc).isoformat(),
    }
    client.table("eval_cases").insert(row).execute()


def _update_eval_run(
    run_id: str,
    pass_count: int,
    fail_count: int,
    avg_latency_ms: int,
    notes: dict,
) -> None:
    client = _get_supabase()
    client.table("eval_runs").update(
        {
            "pass_count": pass_count,
            "fail_count": fail_count,
            "avg_latency_ms": avg_latency_ms,
            "notes": json.dumps(notes),
        }
    ).eq("id", run_id).execute()


# ---------------------------------------------------------------------------
# Suite runner
# ---------------------------------------------------------------------------


async def _run_suite(
    suite: str,
    smoke_ids: set[str] | None,
    no_cache: bool,
    allow_fallback: bool,
) -> dict:
    """
    Run one suite (planner or router).  Returns a summary dict.

    Returns:
        {
          "suite": str,
          "run_id": str,
          "complete": bool,
          "pass_count": int,
          "fail_count": int,
          "not_run_count": int,
          "avg_latency_ms": int,          # excludes cache hits and not-run
          "valid_plan_rate": float,        # planner only
          "case_pass_rate": float,
          "accuracy": float,              # router only
          "passed_ids": list[str],
          "notes": dict,
        }
    """
    from app.eval.planner_eval import PROMPT_VERSION as PLANNER_PROMPT_VERSION
    from app.eval.planner_eval import run_planner
    from app.eval.router_eval import PROMPT_VERSION as ROUTER_PROMPT_VERSION
    from app.eval.router_eval import run_router
    from app.eval.scorers import grade_planner, grade_router
    from app.llm.types import LLMRateLimitError, LLMServerError

    category = suite  # "planner" or "router"
    suite_name = f"{suite}_eval"

    prompt_version = PLANNER_PROMPT_VERSION if suite == "planner" else ROUTER_PROMPT_VERSION

    # --- insert eval_runs row ---
    try:
        run_id = _insert_eval_run(suite_name)
    except Exception as exc:
        logger.error("Failed to insert eval_runs row: %s", exc)
        sys.exit(2)

    golden_rows = _fetch_golden_rows(category)
    if not golden_rows:
        logger.warning("No golden rows found for category=%s", category)

    # Filter to smoke subset if requested
    if smoke_ids:
        golden_rows = [
            r for r in golden_rows if r["expected_output"].get("meta", {}).get("id") in smoke_ids
        ]

    cache = _load_cache() if not no_cache else {}

    pass_count = 0
    fail_count = 0
    not_run_count = 0
    latencies: list[int] = []
    passed_ids: list[str] = []
    valid_plan_count = 0  # planner A1
    consecutive_429s = 0
    complete = True
    models_used: set[str] = set()
    cache_hits = 0

    for row in golden_rows:
        expected = row["expected_output"]
        case_id: str = expected.get("meta", {}).get("id", row["id"])

        # --- cache lookup ---
        ck = _cache_key(
            model="groq",  # primary
            prompt_version=prompt_version,
            temperature=0,
            case_id=case_id,
            input_prompt=row["input_prompt"],
        )
        cached_actual: dict | None = cache.get(ck) if not no_cache else None

        actual: dict
        latency_ms = 0
        was_not_run = False

        if cached_actual is not None:
            actual = cached_actual
            cache_hits += 1
        else:
            # --- 1–2 s pause between live calls ---
            if latencies or cache_hits:
                await asyncio.sleep(INTER_CALL_PAUSE)

            # --- call target with retry / 429 guard ---
            max_attempts = 3
            last_exc: Exception | None = None
            t0 = time.monotonic()
            for attempt in range(1, max_attempts + 1):
                try:
                    if suite == "planner":
                        now_str = expected.get("meta", {}).get("now")
                        actual = await run_planner(row["input_prompt"], now=now_str)
                        models_used.add("groq")
                    else:
                        actual = await run_router(row["input_prompt"])
                        models_used.add("groq")
                    consecutive_429s = 0
                    last_exc = None
                    break
                except LLMRateLimitError as exc:
                    consecutive_429s += 1
                    last_exc = exc
                    if consecutive_429s >= MAX_CONSECUTIVE_429:
                        logger.error(
                            "Quota guard: %d consecutive 429s. Aborting suite.", consecutive_429s
                        )
                        complete = False
                        was_not_run = True
                        break
                    backoff = 2**attempt
                    logger.warning("429 on attempt %d, backoff %ds", attempt, backoff)
                    await asyncio.sleep(backoff)
                except (LLMServerError, Exception) as exc:
                    last_exc = exc
                    if attempt < max_attempts:
                        await asyncio.sleep(2**attempt)
                    else:
                        was_not_run = True
                        break

            latency_ms = int((time.monotonic() - t0) * 1000)

            if was_not_run or last_exc:
                actual = {
                    "error": str(last_exc) if last_exc else "not_run",
                    "type": "not_run",
                }
                not_run_count += 1
                complete = False
            else:
                # cache successful result
                cache[ck] = actual

        # --- grade ---
        if was_not_run or actual.get("type") == "not_run":
            graded_passed: bool | None = None
        elif suite == "planner":
            grade = grade_planner(actual, expected)
            graded_passed = grade.passed
            if grade.valid_plan:
                valid_plan_count += 1
        else:
            grade = grade_router(actual, expected)
            graded_passed = grade.passed

        # --- insert graded case into DB ---
        try:
            _insert_graded_case(row, run_id, actual, graded_passed, latency_ms)
        except Exception as exc:
            logger.error("Supabase write failure, aborting: %s", exc)
            sys.exit(2)

        if graded_passed is True:
            pass_count += 1
            passed_ids.append(case_id)
        elif graded_passed is False:
            fail_count += 1

        if latency_ms > 0 and not was_not_run and cached_actual is None:
            latencies.append(latency_ms)

        if not complete:
            break  # quota guard triggered

    # save updated cache
    _save_cache(cache)

    avg_latency = int(sum(latencies) / len(latencies)) if latencies else 0
    total = pass_count + fail_count  # excludes not_run

    notes = {
        "prompt_version": prompt_version,
        "models_used": sorted(models_used),
        "git_commit": _git_commit(),
        "cache_hits": cache_hits,
        "not_run": not_run_count,
        "incomplete": not complete,
    }

    try:
        _update_eval_run(run_id, pass_count, fail_count, avg_latency, notes)
    except Exception as exc:
        logger.error("Failed to update eval_runs row: %s", exc)
        sys.exit(2)

    result: dict[str, Any] = {
        "suite": suite,
        "run_id": run_id,
        "complete": complete,
        "pass_count": pass_count,
        "fail_count": fail_count,
        "not_run_count": not_run_count,
        "avg_latency_ms": avg_latency,
        "case_pass_rate": pass_count / total if total else 0.0,
        "passed_ids": passed_ids,
        "notes": notes,
    }

    if suite == "planner":
        # Recompute: valid_plan_count is count of rows where A1 passed (check 1 only)
        result["valid_plan_rate"] = valid_plan_count / total if total else 0.0
    else:
        result["accuracy"] = pass_count / total if total else 0.0

    return result


# ---------------------------------------------------------------------------
# Check-results mode
# ---------------------------------------------------------------------------


def _check_results(prompt_version_planner: str, prompt_version_router: str) -> int:
    """Validate last_run.json against thresholds.  Returns exit code."""
    if not LAST_RUN_PATH.exists():
        print("ERROR: docs/eval/last_run.json not found. Run the eval first.")
        return 1

    try:
        data = json.loads(LAST_RUN_PATH.read_text(encoding="utf-8"))
    except Exception as exc:
        print(f"ERROR: last_run.json malformed: {exc}")
        return 1

    errors: list[str] = []

    pv = data.get("prompt_version", "")
    # Accept either single prompt_version or dict
    if isinstance(pv, dict):
        if pv.get("planner") != prompt_version_planner:
            errors.append(
                f"planner prompt_version mismatch: last_run has '{pv.get('planner')}', "
                f"current is '{prompt_version_planner}'"
            )
        if pv.get("router") != prompt_version_router:
            errors.append(
                f"router prompt_version mismatch: last_run has '{pv.get('router')}', "
                f"current is '{prompt_version_router}'"
            )
    # If single string, only check the relevant one
    # (older format; skip detailed check)

    planner = data.get("planner", {})
    router = data.get("router", {})

    vpr = planner.get("valid_plan_rate", 0.0)
    if vpr < PLANNER_VALID_PLAN_THRESHOLD:
        errors.append(
            f"Planner valid_plan_rate {vpr:.2%} < threshold {PLANNER_VALID_PLAN_THRESHOLD:.0%}"
        )

    acc = router.get("accuracy", 0.0)
    if acc < ROUTER_ACCURACY_THRESHOLD:
        errors.append(f"Router accuracy {acc:.2%} < threshold {ROUTER_ACCURACY_THRESHOLD:.0%}")

    # Regression check placeholder: compare against last committed last_run.json on main.
    # (Here we validate the file is structurally sound.)

    if errors:
        for e in errors:
            print(f"FAIL: {e}")
        return 1

    print("OK: last_run.json passes all thresholds.")
    print(f"  Planner valid_plan_rate: {vpr:.2%}")
    print(f"  Router accuracy: {acc:.2%}")
    return 0


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


async def _main_async(args: argparse.Namespace) -> int:
    from app.eval.planner_eval import PROMPT_VERSION as PLANNER_PROMPT_VERSION
    from app.eval.router_eval import PROMPT_VERSION as ROUTER_PROMPT_VERSION

    if args.check_results:
        return _check_results(PLANNER_PROMPT_VERSION, ROUTER_PROMPT_VERSION)

    # Load smoke ids if --smoke
    smoke_ids: set[str] | None = None
    if args.smoke:
        if not SMOKE_IDS_PATH.exists():
            print(f"ERROR: smoke ids file not found: {SMOKE_IDS_PATH}")
            return 2
        smoke_ids = {
            line.strip()
            for line in SMOKE_IDS_PATH.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.startswith("#")
        }

    suites = ["planner", "router"] if args.suite == "all" else [args.suite]

    results: dict[str, dict] = {}
    for suite in suites:
        print(f"\n{'=' * 60}")
        print(f"Running suite: {suite}")
        print(f"{'=' * 60}")
        res = await _run_suite(suite, smoke_ids, args.no_cache, args.allow_fallback)
        results[suite] = res
        _print_suite_summary(res)

    all_complete = all(r["complete"] for r in results.values())

    if all_complete:
        _write_last_run(results)
        print(f"\nResults written to {LAST_RUN_PATH}")
    else:
        print("\nWARNING: One or more suites incomplete. last_run.json NOT updated.")

    # Check thresholds
    threshold_ok = True
    planner_res = results.get("planner", {})
    if planner_res:
        vpr = planner_res.get("valid_plan_rate", 0.0)
        if vpr < PLANNER_VALID_PLAN_THRESHOLD:
            print(
                f"THRESHOLD FAIL: planner valid_plan_rate {vpr:.2%} < "
                f"{PLANNER_VALID_PLAN_THRESHOLD:.0%}"
            )
            threshold_ok = False

    router_res = results.get("router", {})
    if router_res:
        acc = router_res.get("accuracy", 0.0)
        if acc < ROUTER_ACCURACY_THRESHOLD:
            print(f"THRESHOLD FAIL: router accuracy {acc:.2%} < {ROUTER_ACCURACY_THRESHOLD:.0%}")
            threshold_ok = False

    if not all_complete:
        return 1
    return 0 if threshold_ok else 1


def _print_suite_summary(res: dict) -> None:
    suite = res["suite"]
    print(f"  run_id       : {res['run_id']}")
    print(f"  pass         : {res['pass_count']}")
    print(f"  fail         : {res['fail_count']}")
    print(f"  not_run      : {res['not_run_count']}")
    print(f"  avg_latency  : {res['avg_latency_ms']} ms")
    print(f"  case_pass_rate: {res['case_pass_rate']:.2%}")
    if suite == "planner":
        print(f"  valid_plan_rate (A1): {res.get('valid_plan_rate', 0):.2%}")
    else:
        print(f"  accuracy     : {res.get('accuracy', 0):.2%}")
    if not res["complete"]:
        print("  *** RUN INCOMPLETE (quota guard triggered) ***")


def _write_last_run(results: dict[str, dict]) -> None:
    """
    Write (or merge into) docs/eval/last_run.json.

    Supports the 20+20 split workflow:
      - Run --suite planner  → writes planner section, keeps existing router section
      - Run --suite router   → writes router section, keeps existing planner section
    Both sections must exist before --check-results passes.
    """
    from app.eval.planner_eval import PROMPT_VERSION as PLANNER_PV
    from app.eval.router_eval import PROMPT_VERSION as ROUTER_PV

    # Load existing file so we can merge (don't clobber the other suite's results)
    existing: dict = {}
    if LAST_RUN_PATH.exists():
        try:
            existing = json.loads(LAST_RUN_PATH.read_text(encoding="utf-8"))
        except Exception:
            existing = {}

    # Start from existing, update only what this run produced
    data = {
        "date": datetime.now(timezone.utc).isoformat(),
        "commit": _git_commit(),
        "prompt_version": {
            "planner": PLANNER_PV,
            "router": ROUTER_PV,
        },
        # Preserve existing suite data as fallback, overwrite only what was just run
        "planner": existing.get(
            "planner",
            {
                "valid_plan_rate": 0.0,
                "case_pass_rate": 0.0,
                "passed_ids": [],
            },
        ),
        "router": existing.get(
            "router",
            {
                "accuracy": 0.0,
                "passed_ids": [],
            },
        ),
    }

    # Overwrite only the suites that were just run
    if "planner" in results:
        pl = results["planner"]
        data["planner"] = {
            "valid_plan_rate": pl.get("valid_plan_rate", 0.0),
            "case_pass_rate": pl.get("case_pass_rate", 0.0),
            "passed_ids": pl.get("passed_ids", []),
        }

    if "router" in results:
        rt = results["router"]
        data["router"] = {
            "accuracy": rt.get("accuracy", 0.0),
            "passed_ids": rt.get("passed_ids", []),
        }

    LAST_RUN_PATH.parent.mkdir(parents=True, exist_ok=True)
    LAST_RUN_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="D26 Eval Runner")
    parser.add_argument("--suite", choices=["planner", "router", "all"], default="all")
    parser.add_argument("--smoke", action="store_true")
    parser.add_argument("--no-cache", action="store_true")
    parser.add_argument("--check-results", action="store_true")
    parser.add_argument("--allow-fallback", action="store_true")
    args = parser.parse_args(argv)

    return asyncio.run(_main_async(args))


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    sys.exit(main())
