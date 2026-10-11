"""Verify exact sentence references, completeness, audience and write scope.

No model-written prose is accepted. This proves grounding in the approved
catalog; correctness of upstream predictions/rules/factors is a separate concern.
"""

import json

from jsonschema import Draft202012Validator

from .prompts import response_schema


def strict_json_loads(text):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("Duplicate JSON key")
            result[key] = value
        return result
    def constant(_):
        raise ValueError("Non-finite JSON value")
    return json.loads(text, object_pairs_hook=pairs, parse_constant=constant)


def verify_plan(plan, catalog):
    if list(Draft202012Validator(response_schema(catalog)).iter_errors(plan)):
        return ["PLAN_SCHEMA_INVALID"]
    issues = []
    if plan["headline_variant"] is not None and type(plan["headline_variant"]) is not int:
        issues.append("HEADLINE_VARIANT_INVALID")
    for audience in ("customer", "manager"):
        cards = {card.id: card for card in getattr(catalog, audience)}
        selected = [entry["id"] for entry in plan[audience]]
        if len(selected) != len(set(selected)) or set(selected) != set(cards):
            issues.append(f"{audience.upper()}_COVERAGE_INVALID")
        for entry in plan[audience]:
            if type(entry["variant"]) is not int or entry["variant"] >= len(cards[entry["id"]].variants):
                issues.append(f"{audience.upper()}_VARIANT_INVALID")
    return sorted(set(issues))


def template_plan(catalog):
    return {
        "headline_variant": 0 if catalog.headlines else None,
        "customer": [{"id": c.id, "variant": 0} for c in catalog.customer],
        "manager": [{"id": c.id, "variant": 0} for c in catalog.manager],
    }


def render(plan, catalog):
    issues = verify_plan(plan, catalog)
    if issues:
        raise ValueError("Cannot render an unverified explanation plan")
    def audience(name):
        cards = {card.id: card for card in getattr(catalog, name)}
        return " ".join(cards[e["id"]].variants[e["variant"]] for e in plan[name]) or None
    index = plan["headline_variant"]
    return {
        "headline": catalog.headlines[index] if index is not None else None,
        "customer_message": audience("customer"), "manager_message": audience("manager"),
    }
