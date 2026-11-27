"""Server-side calls to Supabase that need the service-role key (never exposed to browsers)."""

import httpx

from app.core.config import get_settings
from app.core.errors import ConflictError, ServiceUnavailable


def _require_admin() -> tuple[str, str]:
    s = get_settings()
    if not s.supabase_url or not s.supabase_service_role_key:
        raise ServiceUnavailable("Supabase service credentials are not configured on the server")
    return s.supabase_url.rstrip("/"), s.supabase_service_role_key


def _headers(key: str) -> dict[str, str]:
    return {"apikey": key, "Authorization": f"Bearer {key}"}


def create_auth_user(email: str, password: str, full_name: str) -> str:
    """Create a confirmed Supabase Auth user (GoTrue admin API). Returns the user id."""
    base, key = _require_admin()
    try:
        r = httpx.post(
            f"{base}/auth/v1/admin/users",
            headers=_headers(key),
            json={"email": email, "password": password, "email_confirm": True, "user_metadata": {"full_name": full_name}},
            timeout=15,
        )
    except httpx.TransportError as exc:
        raise ServiceUnavailable("Could not reach Supabase Auth") from exc
    if r.status_code in (200, 201):
        return r.json()["id"]
    if r.status_code == 422 or "already" in r.text.lower():
        raise ConflictError("A user with this email already exists in Supabase Auth")
    raise ServiceUnavailable(f"Supabase Auth rejected the request ({r.status_code})")


def find_auth_user_id(email: str) -> str | None:
    """Look up an existing auth user by email (paginates the admin user list)."""
    base, key = _require_admin()
    page = 1
    while page <= 50:
        r = httpx.get(f"{base}/auth/v1/admin/users", headers=_headers(key), params={"page": page, "per_page": 200}, timeout=15)
        r.raise_for_status()
        users = r.json().get("users", [])
        for u in users:
            if (u.get("email") or "").lower() == email.lower():
                return u["id"]
        if len(users) < 200:
            return None
        page += 1
    return None


def upload_public_object(path: str, content: bytes, content_type: str) -> str:
    """Upload to Supabase Storage (public bucket) and return the public URL."""
    base, key = _require_admin()
    bucket = get_settings().supabase_storage_bucket
    try:
        r = httpx.post(
            f"{base}/storage/v1/object/{bucket}/{path}",
            headers={**_headers(key), "Content-Type": content_type, "x-upsert": "true", "cache-control": "3600"},
            content=content,
            timeout=30,
        )
    except httpx.TransportError as exc:
        raise ServiceUnavailable("Could not reach Supabase Storage") from exc
    if r.status_code not in (200, 201):
        raise ServiceUnavailable(f"Image upload failed ({r.status_code}): {r.text[:200]}")
    return f"{base}/storage/v1/object/public/{bucket}/{path}"


def delete_object(path: str) -> None:
    try:
        base, key = _require_admin()
        bucket = get_settings().supabase_storage_bucket
        httpx.request("DELETE", f"{base}/storage/v1/object/{bucket}", headers=_headers(key), json={"prefixes": [path]}, timeout=15)
    except Exception:  # noqa: BLE001 — orphaned images are harmless
        pass
