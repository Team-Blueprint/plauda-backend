import uuid

PASSWORD = "s3cret-pass"


def _unique_email() -> str:
    return f"ada-{uuid.uuid4().hex[:10]}@plauda-test.local"


async def test_register_login_me(db_client):
    email = _unique_email()
    resp = await db_client.post(
        "/auth/register",
        json={"store_name": "Pytest Ada's Closet", "email": email, "password": PASSWORD},
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["token_type"] == "bearer"
    assert body["user"]["email"] == email
    assert body["user"]["role"] == "owner"
    assert body["user"]["merchant"]["name"] == "Pytest Ada's Closet"
    assert body["user"]["merchant"]["slug"].startswith("pytest-ada-s-closet")
    token = body["access_token"]

    resp = await db_client.post("/auth/login", json={"email": email, "password": PASSWORD})
    assert resp.status_code == 200, resp.text

    resp = await db_client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200, resp.text
    assert resp.json()["merchant"]["slug"] == body["user"]["merchant"]["slug"]


async def test_register_duplicate_email_conflicts(db_client):
    email = _unique_email()
    payload = {"store_name": "Pytest Duplicate", "email": email, "password": PASSWORD}
    first = await db_client.post("/auth/register", json=payload)
    assert first.status_code == 201, first.text

    second = await db_client.post("/auth/register", json=payload)
    assert second.status_code == 409, second.text


async def test_login_with_wrong_password_is_unauthorized(db_client):
    email = _unique_email()
    await db_client.post(
        "/auth/register",
        json={"store_name": "Pytest Login", "email": email, "password": PASSWORD},
    )
    resp = await db_client.post("/auth/login", json={"email": email, "password": "wrong-pass"})
    assert resp.status_code == 401, resp.text


async def test_me_requires_token(db_client):
    resp = await db_client.get("/auth/me")
    assert resp.status_code == 401, resp.text

    resp = await db_client.get("/auth/me", headers={"Authorization": "Bearer not-a-real-token"})
    assert resp.status_code == 401, resp.text
