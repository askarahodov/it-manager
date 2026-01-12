from __future__ import annotations

from contextvars import ContextVar
from typing import Optional

_source_ip: ContextVar[Optional[str]] = ContextVar("audit_source_ip", default=None)


def set_source_ip(value: Optional[str]) -> None:
    _source_ip.set(value)


def get_source_ip() -> Optional[str]:
    return _source_ip.get()
