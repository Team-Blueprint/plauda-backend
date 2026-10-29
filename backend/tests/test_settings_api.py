async def test_settings_defaults(db_client, merchant_auth):
    resp = await db_client.get("/settings", headers=merchant_auth["headers"])
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["currency"] == "USD"
    assert body["refund_cap"] == "0.00"
    assert body["recovery_reminder_enabled"] is True
    assert body["recovery_timeout_minutes"] == 120
    assert body["paypal_connected"] is False
    assert body["chat_link"].endswith(f"/chat/{merchant_auth['merchant']['slug']}")


async def test_settings_update(db_client, merchant_auth):
    headers = merchant_auth["headers"]
    resp = await db_client.patch(
        "/settings",
        json={
            "refund_cap": "50.00",
            "recovery_reminder_enabled": False,
            "recovery_timeout_minutes": 90,
        },
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["refund_cap"] == "50.00"
    assert body["recovery_reminder_enabled"] is False
    assert body["recovery_timeout_minutes"] == 90


async def test_settings_reject_unsupported_currency(db_client, merchant_auth):
    resp = await db_client.patch(
        "/settings", json={"currency": "NGN"}, headers=merchant_auth["headers"]
    )
    assert resp.status_code == 422


async def test_currency_change_blocked_while_products_exist(db_client, merchant_auth):
    headers = merchant_auth["headers"]
    resp = await db_client.post(
        "/products",
        json={"name": "Scarf", "price": "10.00"},
        headers=headers,
    )
    assert resp.status_code == 201, resp.text

    resp = await db_client.patch("/settings", json={"currency": "EUR"}, headers=headers)
    assert resp.status_code == 409
