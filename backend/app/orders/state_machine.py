"""Order status machine — the single source of truth for allowed transitions.

Invariants (BUILD_PLAN §4.2):
- ``paid`` is written by the verified PayPal webhook only. No API path can set it.
- ``fulfilled`` is written by the owner from ``paid``.
- ``expired`` is written by the recovery worker from ``pending_payment``.
"""

ORDER_STATUSES: tuple[str, ...] = (
    "draft",
    "confirmed",
    "pending_payment",
    "paid",
    "fulfilled",
    "cancelled",
    "expired",
)

TERMINAL_STATUSES: frozenset[str] = frozenset({"fulfilled", "cancelled", "expired"})

ALLOWED_TRANSITIONS: dict[str, frozenset[str]] = {
    "draft": frozenset({"confirmed", "cancelled"}),
    "confirmed": frozenset({"pending_payment", "cancelled"}),
    "pending_payment": frozenset({"paid", "cancelled", "expired"}),
    "paid": frozenset({"fulfilled"}),
    "fulfilled": frozenset(),
    "cancelled": frozenset(),
    "expired": frozenset(),
}


class OrderStateError(ValueError):
    pass


def ensure_transition(current: str, new: str, *, trigger: str) -> None:
    """Raise ``OrderStateError`` when ``current -> new`` is not allowed."""
    if new == "paid" and trigger != "webhook":
        raise OrderStateError("Only the verified payment webhook can mark an order paid")
    if new not in ALLOWED_TRANSITIONS.get(current, frozenset()):
        raise OrderStateError(f"Cannot move order from {current!r} to {new!r}")
