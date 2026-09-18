# AgentOps Copilot

MCP-native, multi-agent personal assistant — LangGraph orchestration, Flutter client.

7th-Semester CSE (AI & ML) Capstone Project.
See `docs/AgentOps_Implementation_Manual.docx` (kept outside this repo / attached separately)
for the full Technical Implementation Manual — architecture, schema, day-by-day plan,
acceptance criteria, and risk register.

## Monorepo layout

```
backend/    FastAPI backend — agents, MCP clients, risk gate, voice STT, API routes
mobile/     Flutter client — voice input recorder, approval cards, task composer
dataset/    Risk explanation fine-tuning synthetic dataset & validation suite
training/   Google Colab QLoRA 4-bit fine-tuning scripts for Qwen2.5-1.5B
docs/       Technical manual, architecture docs, viva guides, and diary logs
.github/    CI workflows
```

## Getting started

### Backend
```bash
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

### Mobile
```bash
cd mobile
flutter pub get
flutter run
```

## Branch protection

`main` is protected: PRs required, CI must pass before merge, no direct pushes.
See `CONTRIBUTING.md` (TBD) for the PR workflow.

## Status

Build window: **Mon 24 Aug 2026 – Fri 9 Oct 2026** (41 working days).
Day 1 (24 Aug): repo init, branch protection, CI skeleton — this commit.
