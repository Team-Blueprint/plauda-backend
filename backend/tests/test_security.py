import pytest
from fastapi import HTTPException

from app.auth.security import (
    create_access_token,
    decode_token,
    hash_password,
    verify_password,
)


def test_password_hash_roundtrip():
    hashed = hash_password("correct horse battery staple")
    assert hashed != "correct horse battery staple"
    assert verify_password("correct horse battery staple", hashed)
    assert not verify_password("wrong password", hashed)


def test_verify_password_with_invalid_hash_returns_false():
    assert not verify_password("anything", "not-a-bcrypt-hash")


def test_jwt_roundtrip():
    token = create_access_token(
        user_id="11111111-1111-1111-1111-111111111111",
        merchant_id="22222222-2222-2222-2222-222222222222",
        role="owner",
    )
    payload = decode_token(token)
    assert payload["sub"] == "11111111-1111-1111-1111-111111111111"
    assert payload["merchant_id"] == "22222222-2222-2222-2222-222222222222"
    assert payload["role"] == "owner"
    assert "exp" in payload


def test_tampered_jwt_is_rejected():
    token = create_access_token(user_id="u", merchant_id="m", role="owner")
    with pytest.raises(HTTPException) as exc_info:
        decode_token(token + "tampered")
    assert exc_info.value.status_code == 401
