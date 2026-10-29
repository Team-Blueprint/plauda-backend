async def test_healthz_returns_ok(client):
    resp = await client.get("/healthz")
    assert resp.status_code == 200
    body = resp.json()
    assert body["app"] == "plauda"
    assert body["db"] in {"ok", "not_configured", "error"}
    assert body["status"] in {"ok", "degraded"}
