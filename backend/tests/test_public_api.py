async def test_public_store_meta_needs_no_auth(db_client, merchant_auth):
    slug = merchant_auth["merchant"]["slug"]
    resp = await db_client.get(f"/public/chat/{slug}/meta")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["slug"] == slug
    assert body["name"] == merchant_auth["merchant"]["name"]
    assert body["currency"] == "USD"
    assert body["chat_link"].endswith(f"/chat/{slug}")


async def test_public_store_meta_unknown_slug(db_client):
    resp = await db_client.get("/public/chat/does-not-exist/meta")
    assert resp.status_code == 404
