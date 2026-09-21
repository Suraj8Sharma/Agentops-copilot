# ruff: noqa: E501
import json

from app.eval.ingest_golden import main, plan_changes, validate_file


def test_ingest_valid_file_parses_all_cases(tmp_path):
    f = tmp_path / "valid.jsonl"
    f.write_text(
        json.dumps({"category": "planner", "input": "prompt1", "expected": {}}) + "\n" +
        json.dumps({"category": "router", "input": "prompt2", "expected": {}})
    )
    cases, errors, warnings = validate_file(str(f))
    assert not errors
    assert len(cases) == 2
    assert cases[0]["category"] == "planner"
    assert cases[1]["category"] == "router"

def test_ingest_skips_blank_lines_and_handles_utf8_bom(tmp_path):
    f = tmp_path / "bom.jsonl"
    content = "\n" + json.dumps({"category": "planner", "input": "p1", "expected": 1}) + "\n\n"
    f.write_bytes(b"\xef\xbb\xbf" + content.encode('utf-8'))
    cases, errors, warnings = validate_file(str(f))
    assert not errors
    assert len(cases) == 1

def test_ingest_rejects_invalid_json_line(tmp_path):
    f = tmp_path / "bad.jsonl"
    f.write_text("{bad json\n")
    cases, errors, warnings = validate_file(str(f))
    assert len(errors) == 1
    assert "line 1" in errors[0]

def test_ingest_rejects_unknown_category_with_line_number(tmp_path):
    f = tmp_path / "bad.jsonl"
    f.write_text(json.dumps({"category": "unknown", "input": "p1", "expected": 1}) + "\n")
    cases, errors, warnings = validate_file(str(f))
    assert len(errors) == 1
    assert "line 1" in errors[0]

def test_ingest_rejects_empty_input(tmp_path):
    f = tmp_path / "bad.jsonl"
    f.write_text(json.dumps({"category": "planner", "input": "   ", "expected": 1}) + "\n")
    cases, errors, warnings = validate_file(str(f))
    assert len(errors) == 1
    assert "line 1" in errors[0]
    
def test_ingest_rejects_duplicate_case_in_file(tmp_path):
    f = tmp_path / "bad.jsonl"
    case_str = json.dumps({"category": "planner", "input": "p1", "expected": 1})
    f.write_text(case_str + "\n" + case_str + "\n")
    cases, errors, warnings = validate_file(str(f))
    assert len(errors) == 1
    assert "line 2" in errors[0]
    assert "line 1" in errors[0]

def test_ingest_accepts_column_name_aliases(tmp_path):
    f = tmp_path / "valid.jsonl"
    f.write_text(json.dumps({"category": "planner", "input_prompt": "p1", "expected_output": 1}) + "\n")
    cases, errors, warnings = validate_file(str(f))
    assert not errors
    assert cases[0]["input_prompt"] == "p1"
    assert cases[0]["expected_output"] == 1

def test_ingest_warns_on_unknown_keys_without_failing(tmp_path):
    f = tmp_path / "valid.jsonl"
    f.write_text(json.dumps({"category": "planner", "input": "p1", "expected": 1, "extra": 2}) + "\n")
    cases, errors, warnings = validate_file(str(f))
    assert not errors
    assert len(warnings) == 1
    assert "extra" in warnings[0]

def test_ingest_any_invalid_line_means_nothing_written(monkeypatch, tmp_path):
    f = tmp_path / "bad.jsonl"
    f.write_text(
        json.dumps({"category": "planner", "input": "p1", "expected": 1}) + "\n" +
        "{bad json\n"
    )
    assert main(['--file', str(f)]) == 1

def test_plan_changes_second_run_is_all_unchanged():
    cases = [{"category": "planner", "input_prompt": "p1", "expected_output": {"a": 1, "b": 2}}]
    existing = [{"id": "123", "category": "planner", "input_prompt": "p1", "expected_output": {"b": 2, "a": 1}}]
    plan = plan_changes(cases, existing)
    assert not plan["inserts"]
    assert not plan["updates"]
    assert len(plan["unchanged"]) == 1

def test_plan_changes_updates_expected_output_when_file_changes():
    cases = [{"category": "planner", "input_prompt": "p1", "expected_output": 2}]
    existing = [{"id": "123", "category": "planner", "input_prompt": "p1", "expected_output": 1}]
    plan = plan_changes(cases, existing)
    assert len(plan["updates"]) == 1
    assert plan["updates"][0]["expected_output"] == 2

def test_plan_changes_reports_orphans_without_deleting():
    cases = []
    existing = [{"id": "123", "category": "planner", "input_prompt": "p1", "expected_output": 1}]
    plan = plan_changes(cases, existing)
    assert len(plan["orphans"]) == 1
    
def test_validate_only_needs_no_env_vars(monkeypatch, tmp_path):
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_SERVICE_ROLE_KEY", raising=False)
    f = tmp_path / "valid.jsonl"
    f.write_text(json.dumps({"category": "planner", "input": "p1", "expected": 1}) + "\n")
    assert main(['--file', str(f), '--validate-only']) == 0
