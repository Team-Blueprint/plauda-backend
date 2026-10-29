async def test_business_info_returns_all_sources(db_client, merchant_auth):
    resp = await db_client.get("/business-info", headers=merchant_auth["headers"])
    assert resp.status_code == 200, resp.text
    docs = resp.json()
    assert {doc["source"] for doc in docs} == {"about", "policies", "faq"}
    assert all(doc["content"] == "" for doc in docs)


async def test_business_info_upsert(db_client, merchant_auth):
    headers = merchant_auth["headers"]

    resp = await db_client.put(
        "/business-info/about",
        json={"content": "# About\n\nWe sell hand-dyed silk."},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["content"].startswith("# About")

    resp = await db_client.put(
        "/business-info/about",
        json={"content": "# About\n\nUpdated copy."},
        headers=headers,
    )
    assert resp.status_code == 200
    assert "Updated copy." in resp.json()["content"]

    resp = await db_client.get("/business-info", headers=headers)
    about = next(doc for doc in resp.json() if doc["source"] == "about")
    assert "Updated copy." in about["content"]


async def test_business_info_rejects_unknown_source(db_client, merchant_auth):
    resp = await db_client.put(
        "/business-info/shipping", json={"content": "nope"}, headers=merchant_auth["headers"]
    )
    assert resp.status_code == 422
