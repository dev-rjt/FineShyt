"""Grounded customer and relationship-manager explanations."""

from .engine import ExplanationEngine, component_versions
from .providers import OllamaProvider

__all__ = ["ExplanationEngine", "OllamaProvider", "component_versions"]
