async def test_delivery_zone_crud(db_client, merchant_auth):
    headers = merchant_auth["headers"]

    resp = await db_client.post(
        "/delivery-zones",
        json={
            "name": "Lagos Mainland",
            "areas": ["Yaba", "Surulere"],
            "fee": "5.50",
            "eta_days": 2,
        },
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    zone = resp.json()
    assert zone["fee"] == "5.50"
    assert zone["areas"] == ["Yaba", "Surulere"]

    resp = await db_client.get("/delivery-zones", headers=headers)
    assert resp.status_code == 200
    assert any(z["id"] == zone["id"] for z in resp.json())

    resp = await db_client.patch(
        f"/delivery-zones/{zone['id']}", json={"fee": "7.00", "eta_days": 3}, headers=headers
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["fee"] == "7.00"

    resp = await db_client.delete(f"/delivery-zones/{zone['id']}", headers=headers)
    assert resp.status_code == 204
    resp = await db_client.get(f"/delivery-zones/{zone['id']}", headers=headers)
    assert resp.status_code == 404


async def test_delivery_zone_rejects_negative_fee(db_client, merchant_auth):
    resp = await db_client.post(
        "/delivery-zones",
        json={"name": "Bad zone", "fee": "-1.00"},
        headers=merchant_auth["headers"],
    )
    assert resp.status_code == 422
