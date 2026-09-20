import json

from supabase import create_client

from app.core.config import settings

client = create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_ROLE_KEY)
task = client.table('tasks').select('*').order('created_at', desc=True).limit(1).execute().data[0]
print(f"Task: {task['id']} - Status: {task['status']}")

try:
    plan_data = (
        client.table('task_plans')
        .select('*')
        .eq('task_id', task['id'])
        .order('created_at', desc=True)
        .limit(1)
        .execute()
        .data
    )
    if plan_data:
        plan = plan_data[0]
        steps = (
            client.table('plan_steps')
            .select('*')
            .eq('plan_id', plan['id'])
            .order('step_index')
            .execute()
            .data
        )
        print('Steps:')
        for s in steps:
            print(f"  {s['step_index']}: {s.get('tool_name')} - {s.get('status')}")
            print(f"  Output: {json.dumps(s.get('output'), indent=2)}")
    else:
        print('No plan generated.')
except Exception as e:
    print('Error:', e)
