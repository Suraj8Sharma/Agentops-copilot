import glob

for file in glob.glob("app/tests/test_*_mcp.py"):
    with open(file, "r", encoding="utf-8") as f:
        content = f.read()

    content = content.replace(
        "idempotency_key=IDEMPOTENCY_KEY,\n        )",
        'idempotency_key=IDEMPOTENCY_KEY,\n        task_id="unknown",\n    )',
    )

    with open(file, "w", encoding="utf-8") as f:
        f.write(content)
