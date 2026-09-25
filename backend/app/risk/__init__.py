"""Risk and approval gate package for AgentOps Copilot.

Owner: Suraj / Jigyasu
"""

from .approval_gate import evaluate, gate
from .risk_explainer import (
    RiskExplainerService,
    RiskExplanation,
    generate_deterministic_explanation,
)
from .risk_rules import RiskRule, lookup

__all__ = [
    "RiskDecision",
    "RiskExplanation",
    "RiskExplainerService",
    "RiskRule",
    "evaluate",
    "gate",
    "generate_deterministic_explanation",
    "lookup",
]
