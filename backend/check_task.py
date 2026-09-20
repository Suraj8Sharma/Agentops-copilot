import json

from supabase import create_client

from app.core.config import settings

client = create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_ROLE_KEY)
task = client.table('tasks').select('*').order('created_at', desc=True).limit(1).execute().data[0]
print("TASK RECORD:")
print(json.dumps(task, indent=2))
steps = (
    client.table('task_steps')
    .select('*')
    .eq('task_id', task['id'])
    .order('created_at')
    .execute()
    .data
)
print("\nSTEPS:")
for s in steps:
    print(f"{s['step_type']} - {s['status']} - {s.get('error_message')}")
