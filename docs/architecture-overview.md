# AgentOps — How It Works (Architecture Overview)

---

## The Big Picture

AgentOps is an AI assistant that takes a user's request (text or voice) and executes it — creating calendar events, sending emails, filing GitHub issues, posting on Slack — all with human approval for risky actions.

---

## The Three Layers

```
┌─────────────────────────────────────┐
│         Flutter App (UI)            │  ← What the user sees
│   Task Composer, Approval Screen,   │
│   Activity Log, Plan View           │
└──────────────────┬──────────────────┘
                   │ user submits task
                   ▼
┌─────────────────────────────────────┐
│      AgentOps Backend (FastAPI)     │  ← The brain
│                                     │
│  LangGraph Planner:                 │
│  1. intent_classify                 │
│  2. plan                            │
│  3. risk_tag                        │
│  4. execute  ──────────────────┐    │
│                                │    │
└────────────────────────────────│────┘
                                 │ MCP protocol
                                 ▼
┌─────────────────────────────────────┐
│       MCP Session Proxy             │  ← The connection manager
│                                     │
│  Suraj  → his GitHub MCP session   │
│  Ishani → her GitHub MCP session   │
│  Bob    → his Slack MCP session    │
└──────┬──────────┬──────────┬───────┘
       │          │          │
       ▼          ▼          ▼
  GitHub MCP  Slack MCP  Gmail MCP   ← Official MCP Servers
  Server      Server     Server        (do the actual work)
       │          │          │
       ▼          ▼          ▼
  GitHub API  Slack API  Gmail API   ← Real provider APIs
```

---

## Step by Step — What Happens When Suraj Says "File a bug on GitHub"

**Step 1 — Flutter app**
Suraj types "file a bug on my repo" and hits send.
Flutter sends this to the AgentOps backend via API.

**Step 2 — LangGraph Planner runs**
- `intent_classify` → understands this is a "file_issue" request
- `plan` → creates a plan: one step, `github.create_issue`
- `risk_tag` → looks up risk level (medium risk, no approval needed)
- `execute` → time to actually do it

**Step 3 — Execute node calls the MCP Proxy**
The execute node sends a request to our MCP Session Proxy:
```
"Suraj wants to call create_issue with these params"
```

**Step 4 — MCP Proxy does the connection job**
The proxy looks up: "Suraj → his GitHub MCP session"
Forwards the request to Suraj's GitHub MCP Server instance.

**Step 5 — GitHub MCP Server does the work**
The official GitHub MCP Server (running with Suraj's GitHub token) calls the GitHub API and creates the issue.

**Step 6 — Result flows back**
GitHub → MCP Server → Proxy → Execute node → logged to DB → shown in Activity Log on Flutter.

---

## Why the MCP Proxy Exists

Every user connects their GitHub/Slack account via OAuth. That means:
- Suraj has his own GitHub token
- Ishani has her own GitHub token

The official GitHub MCP Server is designed for one person — it starts with one token and uses it for everything.

Our MCP Proxy solves this: it starts a **separate MCP server session per user**, each with that user's own token. When Suraj's task runs, it goes to Suraj's session. When Ishani's task runs, it goes to Ishani's session. They never mix.

---

## What Each Person's Work Connects To

| Owner | They build | Connects to |
|---|---|---|
| Suraj | Backend, LangGraph, MCP Proxy | Supabase DB, MCP Servers |
| Ishani | Approval Screen, Plan View, Dashboard | Real `task_plans`, `plan_steps` data from backend |
| Jigyasu | Voice input, Activity Log | Real `execution_logs` data from backend |
| Sanskriti | Settings, Memory/Preferences | Real `user_preferences` table |
| Shivangi | Digest screen, Manual To-Do | Real `digests` table |

---

## The MCP Servers We Use

| Provider | Server | Who runs it |
|---|---|---|
| GitHub | Official GitHub MCP Server | We run it via our proxy |
| Slack | Official Slack MCP Server | We run it via our proxy |
| Gmail | Official Gmail MCP Server | We run it via our proxy |
| Google Calendar | Official Calendar MCP Server | We run it via our proxy |

We don't write these servers. We just manage the connections to them.

---

## Why This Is Technically Strong

Most MCP apps today (Claude Desktop, Cursor) are **single-user, local** — one person, one machine, one token. Simple.

AgentOps is **multi-user, cloud-hosted, MCP-native** — many users, one backend, each with their own isolated MCP session. This is a harder problem and a more production-grade architecture.

The MCP Session Proxy is what makes this possible.

---

*For questions, ask Suraj.*
