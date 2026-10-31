from cryptography.fernet import Fernet, InvalidToken

from app.config import get_settings
from app.payments.errors import CredentialError


def _fernet() -> Fernet:
    key = get_settings().credential_encryption_key
    if not key:
        raise CredentialError("CREDENTIAL_ENCRYPTION_KEY is not configured")
    try:
        return Fernet(key.encode())
    except (TypeError, ValueError):
        raise CredentialError("CREDENTIAL_ENCRYPTION_KEY is invalid") from None


def encrypt_secret(value: str) -> str:
    return _fernet().encrypt(value.encode()).decode()


def decrypt_secret(value: str) -> str:
    try:
        return _fernet().decrypt(value.encode()).decode()
    except InvalidToken:
        raise CredentialError(
            "Stored credential cannot be decrypted — was the encryption key changed?"
        ) from None
