class ConversationError(Exception):
    """Base domain error for conversation operations. Mapped to HTTP by app.errors."""

    status_code = 422


class ConversationNotFoundError(ConversationError):
    status_code = 404


class ConversationConflictError(ConversationError):
    status_code = 409
