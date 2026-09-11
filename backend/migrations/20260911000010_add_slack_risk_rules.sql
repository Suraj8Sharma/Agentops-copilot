-- Migration: 20260911000010_add_slack_risk_rules
-- Adds missing Slack risk rules from D17 spec.

insert into public.risk_rules (action_type, mcp_server, risk_tier, requires_approval, rationale)
values
    (
        'slack.list_channels',
        'slack',
        'low',
        false,
        'Read-only, no side effects'
    ),
    (
        'slack.add_reaction',
        'slack',
        'low',
        false,
        'Low impact, reversible'
    )
on conflict (action_type, mcp_server) do nothing;
