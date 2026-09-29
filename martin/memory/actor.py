"""Request-scoped authenticated actor for memory-writing Agent tools."""

from contextvars import ContextVar, Token


_actor_id: ContextVar[str | None] = ContextVar("memory_actor_id", default=None)


def current_actor_id() -> str | None:
    return _actor_id.get()


def set_actor_id(actor_id: str | None) -> Token:
    return _actor_id.set(actor_id)


def reset_actor_id(token: Token) -> None:
    _actor_id.reset(token)
