"""FastAPI entrypoint.

D1 scope: skeleton only, no routes yet. Config/env, health-check, and the
Supabase connection land on D3 (Section 14 of the implementation manual).
"""
from fastapi import FastAPI

app = FastAPI(title="AgentOps Copilot API")
