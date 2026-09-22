# ruff: noqa: E501
import argparse
import json
import os
import sys
from typing import Dict, List, Tuple

from supabase import Client, create_client

ALLOWED_CATEGORIES = (
    "planner", "router", "risk_explanation",
    "banner", "oauth_edge_case", "mcp_failure"
)

def validate_file(path: str) -> Tuple[List[Dict], List[str], List[str]]:
    cases = []
    errors = []
    warnings = []

    try:
        with open(path, 'r', encoding='utf-8-sig') as f:
            for i, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                except json.JSONDecodeError:
                    errors.append(f"line {i}: invalid JSON")
                    continue
                
                if not isinstance(data, dict):
                    errors.append(f"line {i}: line is not a JSON object")
                    continue

                category = data.get('category')
                if not isinstance(category, str):
                    errors.append(f"line {i}: category must be a string")
                    continue
                category = category.strip().lower()
                if category not in ALLOWED_CATEGORIES:
                    errors.append(f"line {i}: category '{category}' is not one of: {', '.join(ALLOWED_CATEGORIES)}")
                    continue
                
                input_prompt = data.get('input') if 'input' in data else data.get('input_prompt')
                if input_prompt is None:
                    errors.append(f"line {i}: missing 'input' or 'input_prompt'")
                    continue
                if not isinstance(input_prompt, str) or not input_prompt.strip():
                    errors.append(f"line {i}: input must be a non-empty string")
                    continue
                input_prompt = input_prompt.strip()

                if 'expected' in data:
                    expected_output = data['expected']
                elif 'expected_output' in data:
                    expected_output = data['expected_output']
                else:
                    errors.append(f"line {i}: missing 'expected' or 'expected_output'")
                    continue

                duplicate_found = False
                for case, line_num in cases:
                    if case['category'] == category and case['input_prompt'] == input_prompt:
                        errors.append(f"line {i}: duplicate case (category='{category}', input='{input_prompt}') found, previously at line {line_num}")
                        duplicate_found = True
                        break
                
                known_keys = {'category', 'input', 'input_prompt', 'expected', 'expected_output'}
                unknown_keys = [k for k in data.keys() if k not in known_keys]
                if unknown_keys:
                    warnings.append(f"line {i}: unknown keys: {', '.join(unknown_keys)}")

                if not duplicate_found:
                    cases.append(({
                        'category': category,
                        'input_prompt': input_prompt,
                        'expected_output': expected_output
                    }, i))
                
    except FileNotFoundError:
        errors.append(f"File not found: {path}")
    except Exception as e:
        errors.append(f"Error reading file: {e}")

    return [c[0] for c in cases], errors, warnings

def plan_changes(cases: List[Dict], existing_rows: List[Dict]) -> Dict[str, List[Dict]]:
    inserts = []
    updates = []
    unchanged = []
    orphans = []

    existing_map = {
        (row['category'], row['input_prompt']): row
        for row in existing_rows
    }
    
    cases_set = set()

    for case in cases:
        key = (case['category'], case['input_prompt'])
        cases_set.add(key)
        if key not in existing_map:
            inserts.append(case)
        else:
            existing = existing_map[key]
            if existing.get('expected_output') != case['expected_output']:
                updates.append({
                    'id': existing['id'],
                    'expected_output': case['expected_output']
                })
            else:
                unchanged.append(case)
    
    for row in existing_rows:
        key = (row['category'], row['input_prompt'])
        if key not in cases_set:
            orphans.append(row)
            
    return {
        'inserts': inserts,
        'updates': updates,
        'unchanged': unchanged,
        'orphans': orphans
    }

def load(plan: Dict[str, List[Dict]], client: Client) -> Dict[str, int]:
    summary = {
        'inserted': 0,
        'updated': 0,
        'unchanged': len(plan['unchanged']),
        'orphaned': len(plan['orphans'])
    }
    
    if plan['inserts']:
        res = client.table('eval_cases').insert(plan['inserts']).execute()
        summary['inserted'] = len(res.data)
        
    for update in plan['updates']:
        res = client.table('eval_cases').update({'expected_output': update['expected_output']}).eq('id', update['id']).execute()
        if res.data:
            summary['updated'] += 1

    return summary

def main(argv: List[str] = None) -> int:
    parser = argparse.ArgumentParser(description="Ingest golden eval cases")
    parser.add_argument('--file', type=str, default=os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))), 'docs', 'eval', 'golden_dataset.jsonl'))
    parser.add_argument('--validate-only', action='store_true')
    
    args = parser.parse_args(argv)
    
    cases, errors, warnings = validate_file(args.file)
    
    if errors:
        print(f"File: {args.file}")
        print(f"Lines read: - | valid: {len(cases)} | errors: {len(errors)} | warnings: {len(warnings)}")
        for err in errors:
            print(err)
        for warn in warnings:
            print(f"Warning: {warn}")
        return 1

    cat_counts = {c: 0 for c in ALLOWED_CATEGORIES}
    for case in cases:
        cat_counts[case['category']] += 1
        
    if args.validate_only:
        print(f"File: {args.file}")
        print(f"Lines read: {len(cases)} | valid: {len(cases)} | errors: {len(errors)} | warnings: {len(warnings)}")
        counts_str = ", ".join([f"{c} {cat_counts[c]}" for c in ALLOWED_CATEGORIES])
        print(f"By category: {counts_str}")
        for warn in warnings:
            print(f"Warning: {warn}")
        return 0
        
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    if not url or not key:
        print("Error: SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY must be set.")
        return 2
        
    try:
        client = create_client(url, key)
    except Exception as e:
        print(f"Error creating Supabase client: {e}")
        return 2
        
    try:
        existing = client.table('eval_cases').select('id, category, input_prompt, expected_output').is_('run_id', 'null').execute()
    except Exception as e:
        print(f"Error fetching existing rows: {e}")
        return 2

    plan = plan_changes(cases, existing.data)
    summary = load(plan, client)
    
    print(f"File: {args.file}")
    print(f"Lines read: {len(cases)} | valid: {len(cases)} | errors: {len(errors)} | warnings: {len(warnings)}")
    counts_str = ", ".join([f"{c} {cat_counts[c]}" for c in ALLOWED_CATEGORIES])
    print(f"By category: {counts_str}")
    print(f"Load: inserted {summary['inserted']} | updated {summary['updated']} | unchanged {summary['unchanged']} | orphaned {summary['orphaned']}")
    for warn in warnings:
        print(f"Warning: {warn}")
        
    return 0

if __name__ == "__main__":
    sys.exit(main())
