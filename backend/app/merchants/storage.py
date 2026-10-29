import logging
from functools import lru_cache

import httpx

from app.config import get_settings

logger = logging.getLogger(__name__)


class StorageError(RuntimeError):
    pass


class SupabaseStorage:
    """Thin Supabase Storage REST adapter (no SDK dependency).

    New ``sb_secret_...`` keys are not JWTs. Storage requires an ``Authorization`` header,
    while the platform gateway reads ``apikey`` — send the key on both for compatibility.
    """

    def __init__(self, base_url: str, service_key: str, bucket: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.service_key = service_key
        self.bucket = bucket

    @property
    def is_configured(self) -> bool:
        return bool(self.base_url and self.service_key and self.bucket)

    def _headers(self, extra: dict | None = None) -> dict[str, str]:
        headers = {
            "apikey": self.service_key,
            "Authorization": f"Bearer {self.service_key}",
        }
        if extra:
            headers.update(extra)
        return headers

    def public_url(self, path: str) -> str:
        return f"{self.base_url}/storage/v1/object/public/{self.bucket}/{path}"

    def path_from_public_url(self, url: str) -> str | None:
        prefix = f"{self.base_url}/storage/v1/object/public/{self.bucket}/"
        if not url.startswith(prefix):
            return None
        return url[len(prefix) :]

    async def _request(self, method: str, path: str, **kwargs) -> httpx.Response:
        headers = self._headers(kwargs.pop("headers", None))
        async with httpx.AsyncClient(timeout=30.0) as client:
            return await client.request(method, f"{self.base_url}{path}", headers=headers, **kwargs)

    async def ensure_bucket(self) -> None:
        resp = await self._request("GET", f"/storage/v1/bucket/{self.bucket}")
        if resp.status_code == 200:
            return
        if resp.status_code in (400, 404):
            create = await self._request(
                "POST",
                "/storage/v1/bucket",
                json={"name": self.bucket, "public": True},
            )
            if create.status_code in (200, 201):
                logger.info("created storage bucket %s", self.bucket)
                return
            # Concurrent creation race: the bucket may exist despite the error.
            if create.status_code in (400, 409) and "exist" in create.text.lower():
                return
            raise StorageError(f"bucket create failed: {create.status_code} {create.text[:300]}")
        raise StorageError(f"bucket check failed: {resp.status_code} {resp.text[:300]}")

    async def upload(self, path: str, data: bytes, content_type: str) -> None:
        await self.ensure_bucket()
        resp = await self._request(
            "POST",
            f"/storage/v1/object/{self.bucket}/{path}",
            content=data,
            headers={"Content-Type": content_type, "x-upsert": "false"},
        )
        if resp.status_code not in (200, 201):
            raise StorageError(f"upload failed: {resp.status_code} {resp.text[:300]}")

    async def delete(self, path: str) -> None:
        resp = await self._request("DELETE", f"/storage/v1/object/{self.bucket}/{path}")
        # 404 means already gone — deletion is idempotent for our purposes.
        if resp.status_code not in (200, 204, 404):
            raise StorageError(f"delete failed: {resp.status_code} {resp.text[:300]}")


@lru_cache
def get_storage() -> SupabaseStorage:
    settings = get_settings()
    return SupabaseStorage(
        base_url=settings.supabase_url,
        service_key=settings.supabase_service_key,
        bucket=settings.supabase_storage_bucket,
    )
