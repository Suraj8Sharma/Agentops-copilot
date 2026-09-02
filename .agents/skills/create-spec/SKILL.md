---
name: create-spec
description: Generates a technical specification for a given task, analyzing codebase and existing spec structure in .claude/specs/.
---

# Create Spec Skill

This skill generates a technical specification for a given task by following the established conventions of the project.

## Instructions

1.  **Understand the Request:** Read the user's prompt to understand the task they want a spec for. Ask clarifying questions if the objective or technical details are not clear.
2.  **Analyze Existing Specs:** Use `list_dir` to view `C:\Users\DELL\agentops\.claude\specs\` and `view_file` on existing specs (e.g., `d6-oauth-google.md`, `d8-oauth-callback.md`) to align with the required markdown structure. Common sections include:
    *   Title and Metadata (Project, Plan reference, Owner, File, Status)
    *   Objective
    *   Endpoint Details
    *   Request Details
    *   Behavior / Implementation Steps
    *   Config / Env
    *   Security notes
    *   Error handling
    *   Out of scope
    *   Acceptance / test criteria
    *   Dependencies
3.  **Analyze the Codebase:** As needed, use tools to investigate relevant files in the codebase (e.g., `backend/app/api/...`) to ensure the spec accurately reflects the architecture and data models.
4.  **Generate the Spec:** Write the technical specification using the gathered information, applying the standard format.
5.  **Save the Spec:** Use the `write_to_file` tool to save the generated spec to the `C:\Users\DELL\agentops\.claude\specs\` directory with an appropriate naming convention (e.g., `d9-something.md`).
