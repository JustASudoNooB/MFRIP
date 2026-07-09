"""MFRIP advisor, investor-suitability and portfolio-construction engine.

Layers: profile/risk (1) → constraints (2) → allocation (3) → ranking (4)
→ construction (5) → validation (6). Built incrementally.
"""
from .profile import (
    DebtLoad, DrawdownReaction, EmergencyFund, Employment, Experience,
    ExistingHolding, Goal, InvestorProfile, RiskAssessment, SLEEVES,
    assess_risk, assessment_reasons,
)
from .constraints import Constraint, ConstraintReport, evaluate_constraints

__all__ = [
    "InvestorProfile", "RiskAssessment", "assess_risk", "assessment_reasons",
    "Employment", "Goal", "DrawdownReaction", "Experience", "EmergencyFund",
    "DebtLoad", "ExistingHolding", "SLEEVES",
    "Constraint", "ConstraintReport", "evaluate_constraints",
]
