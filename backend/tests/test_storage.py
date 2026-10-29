import base64
import uuid

import httpx
import pytest

from app.config import get_settings
from app.merchants.constants import IMAGE_CONTENT_TYPES
from app.merchants.storage import SupabaseStorage, get_storage

PNG_1PX = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)


def test_storage_public_url_roundtrip():
    storage = SupabaseStorage("https://proj.supabase.co/", "sb_secret_x", "bucket")
    url = storage.public_url("a/b.png")
    assert url == "https://proj.supabase.co/storage/v1/object/public/bucket/a/b.png"
    assert storage.path_from_public_url(url) == "a/b.png"
    assert storage.path_from_public_url("https://example.com/x.png") is None


def test_storage_is_configured():
    assert not SupabaseStorage("", "", "bucket").is_configured
    assert SupabaseStorage("https://proj.supabase.co", "key", "bucket").is_configured


def test_image_content_types_cover_common_formats():
    assert IMAGE_CONTENT_TYPES["image/png"] == ".png"
    assert IMAGE_CONTENT_TYPES["image/jpeg"] == ".jpg"
    assert "image/svg+xml" not in IMAGE_CONTENT_TYPES


def _storage_configured() -> bool:
    settings = get_settings()
    return bool(settings.supabase_url and settings.supabase_service_key)


@pytest.mark.skipif(not _storage_configured(), reason="Supabase storage not configured")
async def test_bucket_upload_and_delete_roundtrip():
    storage = get_storage()
    path = f"pytest/{uuid.uuid4().hex}.png"
    await storage.upload(path, PNG_1PX, "image/png")

    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.get(storage.public_url(path))
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("image/png")

    await storage.delete(path)


@pytest.mark.skipif(not _storage_configured(), reason="Supabase storage not configured")
async def test_product_image_upload_and_delete_endpoint(db_client, merchant_auth):
    headers = merchant_auth["headers"]
    resp = await db_client.post(
        "/products", json={"name": "Photo product", "price": "9.99"}, headers=headers
    )
    assert resp.status_code == 201, resp.text
    product = resp.json()

    resp = await db_client.post(
        f"/products/{product['id']}/images",
        files={"file": ("tiny.png", PNG_1PX, "image/png")},
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert len(body["image_urls"]) == 1
    url = body["image_urls"][0]
    assert url.startswith(f"{get_settings().supabase_url}/storage/v1/object/public/")

    async with httpx.AsyncClient(timeout=30.0) as client:
        img = await client.get(url)
    assert img.status_code == 200

    resp = await db_client.delete(
        f"/products/{product['id']}/images", params={"url": url}, headers=headers
    )
    assert resp.status_code == 204, resp.text

    resp = await db_client.get(f"/products/{product['id']}", headers=headers)
    assert resp.json()["image_urls"] == []

    await db_client.delete(f"/products/{product['id']}", headers=headers)


@pytest.mark.skipif(not _storage_configured(), reason="Supabase storage not configured")
async def test_product_image_rejects_non_image(db_client, merchant_auth):
    headers = merchant_auth["headers"]
    resp = await db_client.post(
        "/products", json={"name": "Bad image product", "price": "9.99"}, headers=headers
    )
    product = resp.json()

    resp = await db_client.post(
        f"/products/{product['id']}/images",
        files={"file": ("notes.txt", b"hello", "text/plain")},
        headers=headers,
    )
    assert resp.status_code == 422

    await db_client.delete(f"/products/{product['id']}", headers=headers)
