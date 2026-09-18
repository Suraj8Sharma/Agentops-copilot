create policy "execution_logs_owner_insert" on public.execution_logs for insert with check ( task_id in ( select id from public.tasks where user_id = auth.uid() ) );
