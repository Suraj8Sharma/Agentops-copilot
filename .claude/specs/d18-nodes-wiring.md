# D18 - Planner Nodes LLM Wiring

## Objective
Replace the deterministic stubs in `app/agents/nodes.py` (`intent_classify` and `plan`) with real LLM calls using `route_llm_call` from `app.llm.router`.

## Implementation Steps

### 1. `intent_classify` Node
- Change signature to `async def intent_classify(state: AgentState) -> dict[str, Any]`.
- Build a prompt instructing the LLM to classify `state["raw_input"]` into one of the known intents (e.g., `schedule_event`, `file_issue`, `send_email`, `read_calendar`, `unclassified`).
- Call `await route_llm_call(prompt, request_type="routing")`.
- Clean the LLM response (strip whitespace/newlines).
- Fallback to `"unclassified"` if the LLM output is not in the known list.
- Log `plan_created` with `source="llm"` to `execution_logs`.

### 2. `plan` Node
- Change signature to `async def plan(state: AgentState) -> dict[str, Any]`.
- If `intent` is `"unclassified"`, fail early as before.
- Look up the template from the existing `_STUB_PLANS` dictionary for the intent.
- Build a prompt instructing the LLM to act as a planner, providing the user's `raw_input` and the JSON template. Instruct the LLM to extract entities (e.g. emails, titles, dates) and replace the `[placeholder]` strings in the template.
- Call `await route_llm_call(prompt, request_type="planning")`.
- Parse the resulting JSON string. (Strip markdown code blocks if the LLM accidentally includes them).
- Validate the parsed JSON against the `Step` dataclass format.
- If parsing or validation fails, log an error to `execution_logs` and fall back to the raw template (or empty plan) so the graph doesn't crash completely.
- Log the resulting plan to `execution_logs` with `source="llm"`.

### 3. Tests
- Update `tests/test_planner.py` to `pytest.mark.asyncio` for the node tests.
- Mock `route_llm_call` in tests instead of relying on the stub mapping.
