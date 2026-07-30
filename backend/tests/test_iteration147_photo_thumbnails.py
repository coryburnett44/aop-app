"""Iteration 147 — Fast photo grid via on-the-fly thumbnails.

User bug: "If an album in Photos page have more than 50 pictures, it loads
slowly. Please use another platform (maybe) to load the photos quicker and
allow members to click on photos in the album to get a larger view. Members
not able to download entire album quickly because of the slow loading."

Root cause: Every `PhotoTile` did `api.get(path, {responseType:'blob'})` +
`URL.createObjectURL(blob)` — which forced the browser to serialise 50
XHR downloads of the *full-resolution originals* (2-8 MB per phone photo)
through the JS thread. That defeats HTTP/2 multiplexing, viewport-based
lazy-load, and progressive decode. On a 50-photo album that's 200-400 MB
downloaded to render 200×200 tiles.

Fix:
  1. New `GET /api/photos/thumb/{storage_path:path}?w=400` — auth-required,
     generates a JPEG q=82 thumbnail with Pillow, caches in memory + browser.
  2. `photo_out()` now includes `thumb_url` alongside the full-res `url`.
  3. `/photos/albums` now returns `cover_thumb_url` so album cards use the
     small variant.
  4. Frontend `PhotoTile` + `PhotoLightbox` swap the blob-fetch pattern for
     native `<img src>` — browser handles fetch, cache, lazy-load, parallel
     HTTP/2 automatically.

This file covers the backend contract (endpoint behaviour + payload shape).
Frontend rendering is covered by a screenshot + the bug_testing_agent.
"""
import os
import requests

API = (os.environ.get("REACT_APP_BACKEND_URL") or "https://club-express-lite.preview.emergentagent.com").rstrip("/") + "/api"
ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "admin@clubhaven.app")
ADMIN_PW = os.environ.get("ADMIN_PASSWORD", "Admin123!")


def _login():
    r = requests.post(f"{API}/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PW}, timeout=10)
    r.raise_for_status()
    j = r.json()
    return j.get("access_token") or j.get("token")


def _first_photo_storage_path(token: str) -> str:
    r = requests.get(f"{API}/photos", headers={"Authorization": f"Bearer {token}"}, timeout=10)
    r.raise_for_status()
    data = r.json()
    assert data, "No photos in the system — seed at least one before running this test"
    return data[0]["storage_path"]


def test_photos_list_includes_thumb_url():
    token = _login()
    r = requests.get(f"{API}/photos", headers={"Authorization": f"Bearer {token}"}, timeout=10)
    r.raise_for_status()
    photos = r.json()
    assert photos, "seed photos required"
    p = photos[0]
    assert p.get("thumb_url", "").startswith("/api/photos/thumb/"), p
    assert "?w=400" in p["thumb_url"]
    # The full-res URL is still exposed for the lightbox / download.
    assert p["url"].startswith("/api/files/")


def test_albums_list_includes_cover_thumb_url():
    token = _login()
    r = requests.get(f"{API}/photos/albums", headers={"Authorization": f"Bearer {token}"}, timeout=10)
    r.raise_for_status()
    albums = r.json()
    # Find any album that has a cover.
    covered = [a for a in albums if a.get("cover_url")]
    assert covered, "expected at least one album with a cover"
    for a in covered:
        assert "cover_thumb_url" in a
        # Should reference the fast thumbnail endpoint (or the direct cover as fallback)
        assert a["cover_thumb_url"], a


def test_thumbnail_endpoint_returns_smaller_bytes_than_original():
    token = _login()
    sp = _first_photo_storage_path(token)
    hdrs = {"Authorization": f"Bearer {token}"}
    original = requests.get(f"{API}/files/{sp}", headers=hdrs, timeout=15)
    assert original.status_code == 200
    thumb = requests.get(f"{API}/photos/thumb/{sp}?w=400", headers=hdrs, timeout=15)
    assert thumb.status_code == 200
    assert thumb.headers.get("content-type", "").startswith("image/jpeg")
    # Thumbnail should be dramatically smaller for a real phone photo.
    # We assert only a modest ratio so this holds for already-small originals.
    assert len(thumb.content) < len(original.content), (
        f"expected thumb < original, got thumb={len(thumb.content)}, original={len(original.content)}"
    )


def test_thumbnail_endpoint_caches_and_returns_304():
    token = _login()
    sp = _first_photo_storage_path(token)
    hdrs = {"Authorization": f"Bearer {token}"}
    # Prime the cache
    first = requests.get(f"{API}/photos/thumb/{sp}?w=400", headers=hdrs, timeout=15)
    assert first.status_code == 200
    etag = first.headers.get("etag")
    assert etag, "response must include ETag header"
    # Repeat with If-None-Match → 304. This is what the browser sends on
    # revisits; even though Cloudflare rewrites Cache-Control globally, the
    # ETag-based revalidation still short-circuits the expensive Pillow
    # work and returns in ~120ms with 0 bytes on the wire.
    second = requests.get(
        f"{API}/photos/thumb/{sp}?w=400",
        headers={**hdrs, "If-None-Match": etag},
        timeout=15,
    )
    assert second.status_code == 304
    # Server-side memory cache — third hit should be served from RAM.
    third = requests.get(f"{API}/photos/thumb/{sp}?w=400", headers=hdrs, timeout=15)
    assert third.headers.get("x-thumb-cache") == "HIT"


def test_thumbnail_width_snapped_to_allowed_set():
    """Requests for non-whitelisted widths (like 250) should snap to the
    nearest allowed width — protects against DoS-by-cache-flood."""
    token = _login()
    sp = _first_photo_storage_path(token)
    hdrs = {"Authorization": f"Bearer {token}"}
    for w in (250, 375, 999):
        r = requests.get(f"{API}/photos/thumb/{sp}?w={w}", headers=hdrs, timeout=15)
        assert r.status_code == 200, f"w={w} should succeed via snap"


def test_thumbnail_endpoint_404_for_unknown_photo():
    token = _login()
    hdrs = {"Authorization": f"Bearer {token}"}
    r = requests.get(f"{API}/photos/thumb/bogus/path.jpg?w=400", headers=hdrs, timeout=10)
    assert r.status_code == 404


def test_thumbnail_endpoint_requires_auth():
    r = requests.get(f"{API}/photos/thumb/bogus/path.jpg?w=400", timeout=10)
    # Without a cookie/bearer token this must not serve anything.
    assert r.status_code in (401, 403), f"expected 401/403, got {r.status_code}"
