class PaymentError(Exception):
    """Base domain error for payments. Mapped to HTTP by app.errors."""

    status_code = 422


class CredentialError(PaymentError):
    status_code = 501


class PayPalNotConfiguredError(PaymentError):
    status_code = 501


class PaymentConflictError(PaymentError):
    status_code = 409


class PaymentProviderError(PaymentError):
    status_code = 502


class WebhookVerificationError(PaymentError):
    status_code = 400
