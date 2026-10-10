from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class Range:
    low: float
    central: float
    high: float

    def __post_init__(self) -> None:
        if not (self.low <= self.central <= self.high):
            # Allow inverted only when explicitly constructed for reductions
            pass

    @staticmethod
    def constant(value: float) -> Range:
        return Range(value, value, value)

    def widen_by_fraction(self, fraction: float) -> Range:
        if fraction <= 0:
            return self
        return Range(
            self.central * (1 - fraction),
            self.central,
            self.central * (1 + fraction),
        )

    def multiply(self, other: float | Range) -> Range:
        if isinstance(other, (int, float)):
            return Range(self.low * other, self.central * other, self.high * other)
        return Range(
            self.low * other.low,
            self.central * other.central,
            self.high * other.high,
        )

    def divide(self, other: float | Range) -> Range:
        if isinstance(other, (int, float)):
            if other == 0:
                raise ZeroDivisionError("Cannot divide by zero")
            return Range(self.low / other, self.central / other, self.high / other)
        for value in (other.low, other.central, other.high):
            if value == 0:
                raise ZeroDivisionError("Cannot divide by zero")
        return Range(
            self.low / other.low,
            self.central / other.central,
            self.high / other.high,
        )

    def add(self, other: Range) -> Range:
        return Range(
            self.low + other.low,
            self.central + other.central,
            self.high + other.high,
        )

    def subtract(self, other: Range) -> Range:
        """Conservative reduction envelope: baseline - scenario."""
        return Range(
            self.low - other.high,
            self.central - other.central,
            self.high - other.low,
        )


def reduction_from_baseline_scenario(baseline: Range, scenario: Range) -> Range:
    return baseline.subtract(scenario)


def clamp_range_value(value: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, value))
