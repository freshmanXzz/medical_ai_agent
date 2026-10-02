"""A human-turn source, available only while an authenticated agent is running."""

from contextvars import ContextVar, Token
from dataclasses import dataclass


@dataclass(frozen=True)
class MemoryInteraction:
    interaction_id: str
    user_text: str

    def __post_init__(self) -> None:
        if not isinstance(self.interaction_id, str) or not self.interaction_id.strip():
            raise ValueError("A human interaction ID is required")
        if not isinstance(self.user_text, str):
            raise ValueError("Human interaction text must be a string")


_interaction: ContextVar[MemoryInteraction | None] = ContextVar(
    "memory_interaction", default=None
)


def current_interaction() -> MemoryInteraction | None:
    return _interaction.get()


def set_interaction(interaction: MemoryInteraction) -> Token:
    if not isinstance(interaction, MemoryInteraction):
        raise ValueError("A validated human interaction is required")
    return _interaction.set(interaction)


def reset_interaction(token: Token) -> None:
    _interaction.reset(token)
