"""Правила динамических групп.

Требования:
- Простая модель JSON правил (без произвольного SQL).
- Безопасность: разрешаем только белый список полей/операторов.

Поддерживаемый формат:
{
  "op": "and" | "or",
  "rules": [
    {"field":"environment","op":"eq","value":"prod"},
    {"field":"os_type","op":"eq","value":"linux"},
    {"field":"tags.env","op":"eq","value":"prod"},
    {"op":"or","rules":[...]}  // вложенные правила
  ]
}
"""

from __future__ import annotations

from typing import Any, Iterable, Optional

from sqlalchemy import and_, false, or_, true
from sqlalchemy.sql.elements import ColumnElement

from app.db.models import Host

ALLOWED_FIELDS = {"name", "hostname", "environment", "os_type", "username", "port"}
ALLOWED_OPS = {"eq", "neq", "contains", "in"}


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def build_host_filter(rule: Optional[dict[str, Any]]) -> ColumnElement[bool]:
    """Преобразует JSON правило в SQLAlchemy выражение.

    Если правило пустое/None — возвращает true(), то есть "все хосты".
    """

    if not rule:
        return true()

    op = (rule.get("op") or "and").lower()
    rules = rule.get("rules")

    if not isinstance(rules, list) or op not in {"and", "or"}:
        # Некорректное правило => не матчим ничего (безопасное поведение)
        return false()

    compiled: list[ColumnElement[bool]] = []
    for item in rules:
        if not isinstance(item, dict):
            continue
        # вложенный блок
        if "rules" in item:
            compiled.append(build_host_filter(item))
            continue
        field = item.get("field")
        item_op = (item.get("op") or "").lower()
        value = item.get("value")

        expr = _compile_condition(field, item_op, value)
        if expr is not None:
            compiled.append(expr)

    if not compiled:
        return false()

    return and_(*compiled) if op == "and" else or_(*compiled)


def _compile_condition(field: Any, op: str, value: Any) -> Optional[ColumnElement[bool]]:
    if not isinstance(field, str):
        return None

    if field.startswith("tags."):
        tag_key = field.split(".", 1)[1].strip()
        if not tag_key:
            return None
        col = Host.tags[tag_key].as_string()
        return _apply_op(col, op, value)

    if field not in ALLOWED_FIELDS:
        return None

    col = getattr(Host, field)
    return _apply_op(col, op, value)


def _apply_op(col: Any, op: str, value: Any) -> Optional[ColumnElement[bool]]:
    if op not in ALLOWED_OPS:
        return None

    if op == "eq":
        return col == value
    if op == "neq":
        return col != value
    if op == "contains":
        if not isinstance(value, str):
            return None
        return col.ilike(f"%{value}%")
    if op == "in":
        values = _as_list(value)
        if not values:
            return None
        return col.in_(values)
    return None

