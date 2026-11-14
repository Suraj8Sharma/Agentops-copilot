# D29 banner-model quality pass note

**Owner:** Ishani
**Date:** 2026-11-14
**Scope:** backend banner model, banner copy rules, banner output validation

## Objective

Improve the notification banner model so it stays advisory-only, stays within the 80-character UI cap, and rejects unsafe or mismatched output before it can be persisted or displayed.

## Before

The banner-generation tests were passing at the smoke level, but the model did not hard-fail unsafe output. A long or policy-violating LLM response could pass through the validation path and create a banner line with the wrong tone or event match.

## Fixes made

- Hardened `backend/app/notifications/banner_model.py` to validate generated output before returning it.
- Rejected empty, over-length, markdown-like, alarmist, or recommendation-heavy responses.
- Added a deterministic fallback for each supported event type so a failed or invalid model result still produces a safe banner rather than surfacing broken output.
- Logged banner-model execution attempts with the existing `banner_model` audit pattern when task context was available.
- Updated the banner copy-rule and payload docs to reflect the D29 safety pass.

## After

Relevant validation command:

```bash
cd backend
python -m pytest app/tests/test_banner_model.py app/tests/test_notifications.py -q
```

Result:

```text
24 passed, 2 deprecation warnings
```

Lint command:

```bash
python -m ruff check app/notifications/banner_model.py app/tests/test_banner_model.py
```

Result: passed.

## Notes and open items

- The repository snapshot does not include the live banner golden dataset or full CI wiring for `banner_model_eval`; those are harness/infra tasks that need Suraj's repo-side setup and the real eval run.
- The model-side guardrails are now in place and repeatable via pytest, but the full dataset-driven pass-rate and frozen-run regression checks still require the golden banner cases and the eval-run harness to be present in the environment.
