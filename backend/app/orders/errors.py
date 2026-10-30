class OrderError(Exception):
    """Base domain error for order operations. Mapped to an HTTP response by app.errors."""

    status_code = 422


class OrderNotFoundError(OrderError):
    status_code = 404


class OrderConflictError(OrderError):
    status_code = 409
