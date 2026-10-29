from tests.conftest import register_merchant


async def _create_product(db_client, headers, **overrides):
    payload = {
        "name": "Silk scarf",
        "description": "Hand-dyed silk scarf",
        "price": "25.00",
        "image_urls": ["https://example.com/scarf.jpg"],
        "variants": [{"name": "Red", "options": {"color": "red"}, "stock": 4}],
    }
    payload.update(overrides)
    return await db_client.post("/products", json=payload, headers=headers)


async def test_product_crud_with_variants(db_client, merchant_auth):
    headers = merchant_auth["headers"]

    resp = await _create_product(db_client, headers)
    assert resp.status_code == 201, resp.text
    product = resp.json()
    assert product["price"] == "25.00"  # money is a decimal string
    assert product["currency"] == merchant_auth["merchant"]["currency"]
    assert product["active"] is True
    assert len(product["variants"]) == 1
    assert product["variants"][0]["stock"] == 4

    resp = await db_client.get("/products", headers=headers)
    assert resp.status_code == 200
    assert any(p["id"] == product["id"] for p in resp.json())

    resp = await db_client.patch(
        f"/products/{product['id']}",
        json={"price": "30.00", "active": False},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["price"] == "30.00"
    assert resp.json()["active"] is False

    # Inactive products are hidden by default.
    resp = await db_client.get("/products", headers=headers)
    assert all(p["id"] != product["id"] for p in resp.json())
    resp = await db_client.get("/products?include_inactive=true", headers=headers)
    assert any(p["id"] == product["id"] for p in resp.json())

    resp = await db_client.delete(f"/products/{product['id']}", headers=headers)
    assert resp.status_code == 204
    resp = await db_client.get(f"/products/{product['id']}", headers=headers)
    assert resp.status_code == 404


async def test_variant_endpoints(db_client, merchant_auth):
    headers = merchant_auth["headers"]
    resp = await _create_product(db_client, headers, variants=[])
    product = resp.json()

    resp = await db_client.post(
        f"/products/{product['id']}/variants",
        json={"name": "Blue", "options": {"color": "blue"}, "price_override": "27.50", "stock": 2},
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    variant = resp.json()
    assert variant["price_override"] == "27.50"

    resp = await db_client.patch(
        f"/products/{product['id']}/variants/{variant['id']}",
        json={"stock": 10},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["stock"] == 10

    resp = await db_client.delete(
        f"/products/{product['id']}/variants/{variant['id']}", headers=headers
    )
    assert resp.status_code == 204


async def test_product_currency_rules(db_client, merchant_auth):
    headers = merchant_auth["headers"]

    resp = await _create_product(db_client, headers, currency="NGN")
    assert resp.status_code == 422

    resp = await _create_product(db_client, headers, currency="EUR")
    assert resp.status_code == 422


async def test_product_image_limit(db_client, merchant_auth):
    headers = merchant_auth["headers"]
    resp = await _create_product(
        db_client, headers, image_urls=[f"https://example.com/{i}.jpg" for i in range(6)]
    )
    assert resp.status_code == 422


async def test_products_are_tenant_scoped(db_client, merchant_auth):
    resp = await _create_product(db_client, merchant_auth["headers"])
    product = resp.json()

    other = await register_merchant(db_client)
    resp = await db_client.get(f"/products/{product['id']}", headers=other["headers"])
    assert resp.status_code == 404
