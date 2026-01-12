from __future__ import annotations

import uuid
from contextvars import ContextVar

request_id_ctx: ContextVar[str | None] = ContextVar("request_id", default=None)


def new_request_id() -> str:
    return uuid.uuid4().hex


def get_request_id() -> str | None:
    return request_id_ctx.get()


def set_request_id(value: str | None) -> None:
    request_id_ctx.set(value)

