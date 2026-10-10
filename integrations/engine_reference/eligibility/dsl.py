from __future__ import annotations

from typing import Any, Optional


class MissingFieldError(Exception):
    def __init__(self, fields: set[str]) -> None:
        self.fields = fields
        super().__init__(f"Missing fields: {fields}")


def _resolve_value(value: Any, thresholds: dict[str, Any]) -> Any:
    if isinstance(value, str) and value.startswith("$thr."):
        key = value[5:]
        return thresholds.get(key)
    return value


def _get_field(ctx: dict[str, Any], field: str) -> Any:
    if field not in ctx:
        return None
    return ctx[field]


def _is_missing(val: Any) -> bool:
    return val is None


def eval_leaf(
    node: dict[str, Any],
    ctx: dict[str, Any],
    thresholds: dict[str, Any],
    missing: set[str],
) -> bool:
    field = node.get("field")
    op = node.get("op")
    if field is None or op is None:
        raise ValueError(f"Invalid leaf node: {node}")

    raw = _get_field(ctx, field)
    if _is_missing(raw):
        missing.add(field)

    value = _resolve_value(node.get("value"), thresholds)

    if op == "is_null":
        return _is_missing(raw)
    if op == "not_null":
        return not _is_missing(raw)
    if _is_missing(raw):
        return False

    if op == "eq":
        return raw == value
    if op == "ne":
        return raw != value
    if op == "in":
        return raw in (value or [])
    if op == "not_in":
        return raw not in (value or [])
    if op == "gt":
        return raw > value
    if op == "gte":
        return raw >= value
    if op == "lt":
        return raw < value
    if op == "lte":
        return raw <= value
    if op == "is_true":
        return raw is True
    if op == "is_false":
        return raw is False
    if op == "contains":
        return value in (raw or [])
    if op == "not_contains":
        return value not in (raw or [])

    raise ValueError(f"Unknown op: {op}")


def eval_condition(
    node: dict[str, Any] | list[Any] | None,
    ctx: dict[str, Any],
    thresholds: dict[str, Any],
    missing: set[str],
) -> bool:
    if node is None:
        return False
    if isinstance(node, list):
        return all(
            eval_condition(n, ctx, thresholds, missing) for n in node if isinstance(n, dict)
        )

    if "all" in node:
        return all(
            eval_condition(c, ctx, thresholds, missing)
            for c in node["all"]
        )
    if "any" in node:
        return any(
            eval_condition(c, ctx, thresholds, missing)
            for c in node["any"]
        )
    if "not" in node:
        inner = node["not"]
        if isinstance(inner, list):
            return not eval_condition({"all": inner}, ctx, thresholds, missing)
        return not eval_condition(inner, ctx, thresholds, missing)

    if "field" in node:
        return eval_leaf(node, ctx, thresholds, missing)

    return False


def condition_uses_fields(node: Any, acc: set[str] | None = None) -> set[str]:
    acc = acc or set()
    if isinstance(node, dict):
        if "field" in node:
            acc.add(node["field"])
        for v in node.values():
            condition_uses_fields(v, acc)
    elif isinstance(node, list):
        for item in node:
            condition_uses_fields(item, acc)
    return acc
