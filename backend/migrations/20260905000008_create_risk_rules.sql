-- Migration: 20260905000008_create_risk_rules
-- Creates and seeds the risk_rules table.
-- risk_rules is the hardcoded safety table - written ONLY by migrations,
-- never by the running application or any LLM at runtime.
-- Idempotent: yes  Destructive: no

-- ---------------------------------------------
-- 1. Table
-- ---------------------------------------------

create table if not exists public.risk_rules (
    id                 serial      not null,
    action_type        text        not null,
    mcp_server         text        not null,
    risk_tier          text        not null,
    requires_approval  boolean     not null,
    rationale          text,
    constraint risk_rules_pkey primary key (id),
    constraint risk_rules_action_type_mcp_server_unique
        unique (action_type, mcp_server),
    constraint risk_rules_mcp_server_check
        check (mcp_server in ('calendar', 'gmail', 'github', 'slack')),
    constraint risk_rules_risk_tier_check
        check (risk_tier in ('low', 'medium', 'high'))
);

-- ---------------------------------------------
-- 2. Row Level Security
-- ---------------------------------------------

alter table public.risk_rules enable row level security;

-- Authenticated users may read all rows (the planner needs to perform
-- lookups on behalf of any user).  No INSERT / UPDATE / DELETE policy
-- for the client role - blocked by default (fail-closed at the DB layer too).
drop policy if exists "risk_rules_authenticated_select" on public.risk_rules;
create policy "risk_rules_authenticated_select" on public.risk_rules
    for select
    using (true);

-- ---------------------------------------------
-- 3. Seed Data (canonical 10 rows)
--    ON CONFLICT DO NOTHING makes this idempotent.
-- ---------------------------------------------

insert into public.risk_rules (action_type, mcp_server, risk_tier, requires_approval, rationale)
values
    (
        'calendar.list_events',
        'calendar',
        'low',
        false,
        'Read-only, no side effects'
    ),
    (
        'calendar.create_event_internal_only',
        'calendar',
        'medium',
        false,
        'Reversible; all attendees on a known/internal domain'
    ),
    (
        'calendar.create_event_external_attendee',
        'calendar',
        'high',
        true,
        'Involves a party outside the organisation; needs confirmation before external visibility'
    ),
    (
        'calendar.delete_event',
        'calendar',
        'high',
        true,
        'Destructive and not easily reversible for the invitee''s view'
    ),
    (
        'gmail.create_draft',
        'gmail',
        'low',
        false,
        'Nothing leaves the user''s account'
    ),
    (
        'gmail.send_message',
        'gmail',
        'high',
        true,
        'Irreversible the moment it is sent'
    ),
    (
        'github.create_issue',
        'github',
        'medium',
        false,
        'Reversible - can be closed/edited'
    ),
    (
        'github.comment_on_issue',
        'github',
        'medium',
        false,
        'Visible externally but editable/deletable'
    ),
    (
        'slack.post_message_dm',
        'slack',
        'medium',
        false,
        'Private; low blast radius'
    ),
    (
        'slack.post_message_channel',
        'slack',
        'high',
        true,
        'Instantly visible to a whole workspace'
    )
on conflict (action_type, mcp_server) do nothing;
