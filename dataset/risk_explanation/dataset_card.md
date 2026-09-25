# Dataset Card: AgentOps Risk Explanation Dataset (v1.0)

## Dataset Summary

The **AgentOps Risk Explanation Dataset** is a curated, instruction-tuning dataset designed to train a compact open-source language model (1B–2B parameters) using LoRA/QLoRA on consumer/free GPU hardware (e.g., Google Colab T4). The model generates **advisory-only** plain-English explanations for actions flagged by AgentOps' hardcoded safety policy.

- **Primary Maintainer:** Jigyasu & Ishani
- **Project:** AgentOps Copilot (7th-Semester CSE Capstone)
- **Dataset Version:** `1.0.0`
- **Total Records:** 120
- **Train / Validation Split:** 96 Train (80%) / 24 Validation (20%)
- **Data Format:** JSON Lines (`.jsonl`)

---

## Category Distribution

| Category | Description | Train Count | Val Count | Total |
| :--- | :--- | :---: | :---: | :---: |
| `email_send` | Outbound external emails | 11 | 3 | 14 |
| `email_draft` | In-progress drafts (low risk) | 6 | 0 | 6 |
| `calendar_external` | Invites with external attendees | 5 | 2 | 7 |
| `calendar_delete` | Destructive meeting cancellations | 5 | 3 | 8 |
| `calendar_conflict` | Meetings overlapping busy slots | 4 | 1 | 5 |
| `github_issue_create` | Public/repo issue creation | 6 | 0 | 6 |
| `github_destructive` | Branch/repository deletions | 9 | 1 | 10 |
| `slack_broadcast` | Messages to public channels | 5 | 0 | 5 |
| `read_only` | Data retrieval queries | 6 | 1 | 7 |
| `ambiguous_input` | Missing dates/recipients | 8 | 4 | 12 |
| `sensitive_data` | Secrets / database dumps | 4 | 2 | 6 |
| `bulk_operations` | Broadcasts & multi-entity actions | 2 | 2 | 4 |
| `prompt_injection_defense` | Adversarial rule override attempts | 6 | 2 | 8 |
| `hindi_hinglish` | Hindi & code-mixed Hinglish voice requests | 15 | 2 | 17 |
| `multi_step_chain` | Chained multi-tool workflows | 4 | 1 | 5 |
| **Total** | | **96** | **24** | **120** |

---

## Safety Guidelines: Safe vs. Unsafe Outputs

### Safe Output Example
```json
{
  "summary": "AgentOps is preparing to send an email to Professor Rawat with project_report.pdf attached.",
  "reason": "Sending an external email is an irreversible action and therefore requires your confirmation.",
  "verify_before_approval": [
    "Confirm the recipient address (prof_rawat@university.edu)",
    "Review the email content and attachment",
    "Confirm submission deadline"
  ]
}
```

### Unsafe Output Example (PROHIBITED)
```json
{
  "summary": "Sending email to professor.",
  "requires_approval": false,  // <-- VIOLATION: Model attempted to decide approval!
  "decision": "approved",       // <-- VIOLATION: Model attempted to bypass human checkpoint!
  "reason": "This email looks safe so I am auto-approving it."
}
```

---

## Ethical & Privacy Considerations
- **Zero PII:** All names, email domains, repositories, and meeting topics are synthetic or publicly generic academic examples.
- **Academic License:** Open for capstone review, viva demonstrations, and reproducibility under the MIT license.
