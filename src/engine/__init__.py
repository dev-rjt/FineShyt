"""Deterministic product screening and sustainability impact calculations.

The engine deliberately contains no model or LLM code.  Callers must provide
versioned factor and assumption records loaded by the data/database layer.
"""

from .gate import evaluate_gate
from .impact import estimate_impact

__all__ = ["estimate_impact", "evaluate_gate"]
