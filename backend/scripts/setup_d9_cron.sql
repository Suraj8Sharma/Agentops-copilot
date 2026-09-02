-- ============================================================================
-- AgentOps Copilot - D9 Token Sweep Cron Job
-- 
-- Run this in the Supabase SQL Editor ONCE YOUR BACKEND IS DEPLOYED.
-- Make sure to replace <YOUR_PRODUCTION_BACKEND_URL> and <YOUR_CRON_SECRET>
-- with your actual live URL and the secret from your .env file.
-- ============================================================================

-- 1. Enable the required extensions
create extension if not exists pg_net;
create extension if not exists pg_cron;

-- 2. Schedule the sweep job to run every 12 hours
select cron.schedule(
  'sweep-google-tokens',
  '0 */12 * * *',
  $$
    select net.http_post(
      url := 'https://<YOUR_PRODUCTION_BACKEND_URL>/oauth/internal/sweep-tokens',
      headers := '{"Authorization": "Bearer <YOUR_CRON_SECRET>"}'::jsonb
    );
  $$
);

-- ============================================================================
-- Helpful maintenance commands (do not run unless needed):
-- 
-- View active jobs:
--   select * from cron.job;
-- 
-- View run history/logs:
--   select * from cron.job_run_details order by start_time desc limit 10;
--
-- Delete the job:
--   select cron.unschedule('sweep-google-tokens');
-- ============================================================================
