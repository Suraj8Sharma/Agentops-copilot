# Design Decision: REST Wrapper vs. MCP-Native Clients for GitHub & Slack

**Date:** 2026-09-08
**Author:** Suraj
**Status:** Decided — REST wrappers for all four providers (Calendar, Gmail, GitHub, Slack)

---

## Context

The original implementation plan (Section 8.2, Technical Implementation Manual) describes all four provider clients — Calendar, Gmail, GitHub, Slack — as "thin wrappers" behind a uniform internal call/response envelope. During D14 planning, we explored whether GitHub and Slack should be built as genuinely MCP-native clients, connecting to real MCP servers (official or community) instead of wrapping the provider REST APIs directly.

---

## What We Evaluated

A real MCP-native client would connect to an external MCP server process via stdio or SSE/HTTP. The client sends JSON-RPC `tools/call` messages; the server translates them to provider API calls and returns results.

We specifically looked for SSE/HTTP MCP servers for GitHub and Slack that support per-request authentication — i.e., multi-tenant operation where each user's OAuth token is injected at the HTTP request level, not at server startup.

---

## Why We Chose REST Wrappers

### 1. No mature multi-tenant MCP server exists for GitHub or Slack

The official `@modelcontextprotocol/server-github` and `@modelcontextprotocol/server-slack` (from `modelcontextprotocol/servers`) are built for single-user, local use (Claude Desktop). They expect a single token via environment variables at process startup — `GITHUB_TOKEN`, `SLACK_TOKEN`. They have no mechanism to accept a different token per HTTP request.

Community SSE-capable alternatives exist but are maintained by individuals, have no multi-tenancy, and require forking to route per-user tokens.

### 2. Per-user subprocess spawning is incompatible with free-tier constraints (Section 2.3)

The only workable approach for true MCP-native multi-tenancy using the existing servers would be spawning a separate stdio subprocess per user per tool call, injecting each user's decrypted OAuth token into the subprocess environment at launch time.

This is incompatible with Render's free-tier memory limits and introduces cold-start latency on every tool invocation — unacceptable for the demo path (Section 1.3).

### 3. "Building a multi-tenant MCP proxy" is just a REST wrapper with extra steps

Making any of the existing SSE servers multi-tenant requires forking them, adding a token-extraction layer from incoming HTTP auth headers, and routing that token to downstream API calls. This is functionally identical to what our REST wrappers already do — except it also adds a network hop to an external process and a dependency on a forked, unmaintained third-party server.

### 4. The uniform envelope (Section 8.2) already provides the protocol abstraction

The `call(tool_name, mcp_server, input_params, idempotency_key)` → `{status, output, error, latency_ms}` contract gives the planner and risk gate a provider-agnostic interface. Nothing about this envelope requires an actual MCP protocol wire format underneath — the planner doesn't know or care whether `calendar_client.call(...)` talks JSON-RPC or REST.

If and when a genuinely multi-tenant, hosted MCP server for GitHub or Slack becomes available (expected as the ecosystem matures), the wrapper can be replaced by an MCP SDK client behind the same envelope interface with no changes to the planner, risk gate, or state schema.

---

## Tradeoffs Accepted

| Concern | Our position |
|---------|-------------|
| Not "real MCP" for GitHub/Slack | Accepted. The planner talks to MCP-shaped contracts; wire format is an implementation detail of the client. |
| Missing MCP dynamic tool discovery for risk_tag | Not a regression — our `risk_rules` table is intentionally static and fail-closed. Dynamic discovery would require additional trust decisions we have not designed for. |
| Future swap cost | Low. The wrapper's public interface matches what an MCP SDK client would expose. Replacement is one file, not a graph rewrite. |

---

## Decision

**All four provider clients (Calendar, Gmail, GitHub, Slack) are REST API wrappers** behind the Section 8.2 envelope. This is the correct choice for this project's constraints and timeline. Revisit if a hosted, multi-tenant MCP server for GitHub/Slack ships before the D41 deadline.
