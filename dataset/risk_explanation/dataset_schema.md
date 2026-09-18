# Risk-Explanation Training Dataset Schema (v1.0)

**Project:** AgentOps Copilot  
**Author / Collaborators:** Jigyasu & Ishani  
**Purpose:** Instruction-tuning dataset for a lightweight LoRA fine-tuned language model that generates advisory explanations for actions flagged by AgentOps deterministic risk rules.

---

## 1. Architectural Role & Safety Guarantees

```
                                  +-------------------------------------+
                                  | Hardcoded Deterministic Risk Policy |
                                  | (Sole Authority on requires_approval)|
                                  +-------------------+-----------------+
                                                      |
                                           requires_approval == True
                                                      |
                                                      v
+------------------+                    +-------------------------------+
| User Spoken/Typed|                   | Advisory Small LLM (LoRA)     |
| Request          +------------------>+ - Action Summary               |
+------------------+                   | - Policy Rationale            |
                                       | - Pre-approval Checklist      |
                                       +-------------------------------+
```

- **Invariant:** The LLM is strictly advisory. It never decides, alters, or overrides `requires_approval`.
- **Groundedness:** Explanations must strictly reflect the `planned_action` and `matched_rule` without inventing unmentioned attendees, dates, or implications.

---

## 2. JSON Record Specification

Each line in `train.jsonl` and `val.jsonl` is a standalone JSON object adhering to this schema:

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "title": "RiskExplanationRecord",
  "type": "object",
  "required": ["id", "category", "instruction", "input", "output"],
  "properties": {
    "id": {
      "type": "string",
      "pattern": "^risk_[0-9]{4}$",
      "description": "Unique record identifier"
    },
    "category": {
      "type": "string",
      "description": "Task domain or safety evaluation category"
    },
    "instruction": {
      "type": "string",
      "description": "System prompt / instruction template"
    },
    "input": {
      "type": "object",
      "required": ["user_request", "planned_action", "matched_rule", "requires_approval"],
      "properties": {
        "user_request": { "type": "string" },
        "planned_action": {
          "type": "object",
          "required": ["tool", "operation"],
          "properties": {
            "tool": { "type": "string" },
            "operation": { "type": "string" },
            "recipient": { "type": ["string", "null"] },
            "attachment": { "type": ["string", "null"] },
            "target": { "type": ["string", "null"] },
            "date": { "type": ["string", "null"] },
            "time": { "type": ["string", "null"] }
          }
        },
        "matched_rule": { "type": "string" },
        "requires_approval": { "type": "boolean" }
      }
    },
    "output": {
      "type": "object",
      "required": ["summary", "reason", "verify_before_approval"],
      "properties": {
        "summary": {
          "type": "string",
          "description": "Factual plain-English description of the proposed action."
        },
        "reason": {
          "type": "string",
          "description": "Why the matched hardcoded rule flags this operation."
        },
        "verify_before_approval": {
          "type": "array",
          "items": { "type": "string" },
          "minItems": 1,
          "description": "Checklist of items the user should verify before approving."
        }
      }
    }
  }
}
```

---

## 3. Dataset Distribution Categories

1. `email_send`: Outbound irreversible emails requiring confirmation.
2. `email_draft`: Read/draft actions (low risk / auto-executing baseline).
3. `calendar_external`: Meetings with external participants.
4. `calendar_delete`: Deleting existing meetings (destructive).
5. `calendar_conflict`: Scheduling during existing busy slots.
6. `github_issue_create`: Public/team issue creation.
7. `github_destructive`: Closing/deleting repository milestones or branches.
8. `slack_broadcast`: Posting messages to public Slack channels.
9. `bulk_operations`: Operations impacting multiple entities.
10. `prompt_injection_defense`: Untrusted prompt injection inside user text.
11. `hindi_hinglish`: Multilingual voice/text inputs (Hindi and Hinglish).
12. `ambiguous_input`: Missing or incomplete date/recipient entities.
