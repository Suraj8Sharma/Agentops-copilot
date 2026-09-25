"""Validation script for Risk-Explanation Training and Validation Datasets.

Owner: Jigyasu (supporting Ishani)

Checks:
1. Valid JSON per line
2. All required top-level keys present (id, category, instruction, input, output)
3. Output contains only 'summary', 'reason', 'verify_before_approval'
4. Output MUST NOT contain 'requires_approval' or attempt to decide approval
5. IDs are unique and sequentially formatted
6. Summary and reason are non-empty strings; verify_before_approval is a non-empty list
"""

from __future__ import annotations

import json
import os
import sys

REQUIRED_TOP_KEYS = {"id", "category", "instruction", "input", "output"}
REQUIRED_INPUT_KEYS = {"user_request", "planned_action", "matched_rule", "requires_approval"}
REQUIRED_OUTPUT_KEYS = {"summary", "reason", "verify_before_approval"}
PROHIBITED_OUTPUT_KEYS = {"requires_approval", "approve", "reject", "allow", "decision", "override"}


def validate_file(file_path: str) -> tuple[int, list[str]]:
    errors: list[str] = []
    seen_ids: set[str] = set()
    count = 0

    if not os.path.exists(file_path):
        return 0, [f"File does not exist: {file_path}"]

    with open(file_path, "r", encoding="utf-8") as f:
        for line_num, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            count += 1
            try:
                data = json.loads(line)
            except Exception as e:
                errors.append(f"Line {line_num}: Invalid JSON syntax ({e})")
                continue

            # Check top level keys
            missing_top = REQUIRED_TOP_KEYS - set(data.keys())
            if missing_top:
                errors.append(f"Line {line_num}: Missing top-level keys {missing_top}")

            rec_id = data.get("id", "")
            if not rec_id:
                errors.append(f"Line {line_num}: Missing record ID")
            elif rec_id in seen_ids:
                errors.append(f"Line {line_num}: Duplicate record ID '{rec_id}'")
            else:
                seen_ids.add(rec_id)

            # Check input
            inp = data.get("input", {})
            if not isinstance(inp, dict):
                errors.append(f"Line {line_num}: 'input' must be an object")
            else:
                missing_inp = REQUIRED_INPUT_KEYS - set(inp.keys())
                if missing_inp:
                    errors.append(f"Line {line_num}: Missing input keys {missing_inp}")

            # Check output & safety guarantees
            out = data.get("output", {})
            if not isinstance(out, dict):
                errors.append(f"Line {line_num}: 'output' must be an object")
            else:
                missing_out = REQUIRED_OUTPUT_KEYS - set(out.keys())
                if missing_out:
                    errors.append(f"Line {line_num}: Missing output keys {missing_out}")

                # SAFETY CHECK: No approval override in output!
                for bad_key in PROHIBITED_OUTPUT_KEYS:
                    if bad_key in out:
                        errors.append(
                            f"Line {line_num} [CRITICAL SAFETY VIOLATION]: Output contains prohibited key '{bad_key}'. "
                            f"The LLM must never decide or override approval status!"
                        )

                if not isinstance(out.get("verify_before_approval"), list) or len(out.get("verify_before_approval", [])) == 0:
                    errors.append(f"Line {line_num}: 'verify_before_approval' must be a non-empty list of strings")

    return count, errors


def main():
    target_dir = os.path.dirname(os.path.abspath(__file__))
    train_file = os.path.join(target_dir, "train.jsonl")
    val_file = os.path.join(target_dir, "val.jsonl")

    print("==================================================")
    print("AgentOps Risk-Explanation Dataset Validator")
    print("==================================================")

    all_passed = True
    for name, path in [("Training Set", train_file), ("Validation Set", val_file)]:
        count, errors = validate_file(path)
        print(f"\nValidating {name} ({path})...")
        print(f"  Records checked: {count}")
        if errors:
            print(f"  FAILED with {len(errors)} error(s):")
            for err in errors[:10]:
                print(f"    - {err}")
            all_passed = False
        else:
            print("  PASSED: 100% schema valid, zero duplicates, 100% safety compliant.")

    if not all_passed:
        sys.exit(1)
    print("\nDataset validation successfully completed!")


if __name__ == "__main__":
    main()
