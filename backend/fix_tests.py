import glob

for file in glob.glob("app/tests/*.py"):
    with open(file, "r", encoding="utf-8") as f:
        content = f.read()

    content = content.replace('"app.agents.nodes.supabase"', '"app.agents.nodes.supabase_admin"')
    content = content.replace('"app.agents.runner.supabase"', '"app.agents.runner.supabase_admin"')

    with open(file, "w", encoding="utf-8") as f:
        f.write(content)
