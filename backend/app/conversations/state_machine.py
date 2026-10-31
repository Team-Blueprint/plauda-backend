"""Conversation status machine.

- ``handoff_requested`` is set by the visitor's "Talk to a human" button (and later the
  handoff classifier).
- ``human_active`` / ``ai`` are owner-controlled.
- ``closed`` is terminal.
"""

CONVERSATION_STATUSES: tuple[str, ...] = ("ai", "handoff_requested", "human_active", "closed")

ALLOWED_TRANSITIONS: dict[str, frozenset[str]] = {
    "ai": frozenset({"handoff_requested", "closed"}),
    "handoff_requested": frozenset({"human_active", "closed"}),
    "human_active": frozenset({"ai", "closed"}),
    "closed": frozenset(),
}


class ConversationStateError(ValueError):
    pass


def ensure_transition(current: str, new: str) -> None:
    if new not in ALLOWED_TRANSITIONS.get(current, frozenset()):
        raise ConversationStateError(f"Cannot move conversation from {current!r} to {new!r}")
