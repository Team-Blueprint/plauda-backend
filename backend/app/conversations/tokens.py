import hashlib
import hmac
import secrets


def hash_visitor_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def new_visitor_token() -> tuple[str, str]:
    """Return ``(raw_token, token_hash)`` — only the hash is stored."""
    token = secrets.token_urlsafe(32)
    return token, hash_visitor_token(token)


def token_matches(raw_token: str, stored_hash: str | None) -> bool:
    if not stored_hash:
        return False
    return hmac.compare_digest(hash_visitor_token(raw_token), stored_hash)
