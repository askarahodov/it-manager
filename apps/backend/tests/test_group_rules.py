from sqlalchemy.dialects import postgresql

from app.services.group_rules import build_host_filter


def test_dynamic_group_rules_compile():
    rule = {
        "op": "and",
        "rules": [
            {"field": "environment", "op": "eq", "value": "prod"},
            {"field": "os_type", "op": "eq", "value": "linux"},
            {"field": "tags.env", "op": "eq", "value": "prod"},
        ],
    }
    expr = build_host_filter(rule)
    sql = str(expr.compile(dialect=postgresql.dialect()))
    assert "environment" in sql
    assert "os_type" in sql
    assert "tags" in sql

