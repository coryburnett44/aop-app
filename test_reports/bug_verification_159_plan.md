# Focused Test Plan — Iteration 159 Photo ZIP Download / Cloudflare 520 Cascade

No relevant testing skill found.

## Exact user-reported bug
On Production, downloading 4 photos from the Photos page / `5-Year Anniversary` album showed `Download failed`; after refresh the user was kicked out, and login returned Cloudflare 520 / origin parse error.

## Affected flow
Authenticated admin/member visits `/photos`, opens an album, downloads either selected photos or the album ZIP; backend `/api/photos/download-zip` must stream a valid ZIP and never crash the worker/session.

## Fix/code to inspect
- `/app/backend/routes/photos.py` `download_photos_zip` streaming ZIP rewrite and guardrails.
- `/app/frontend/src/pages/Photos.jsx` blob error unwrapping and download buttons.
- `/app/backend/server.py` object storage/auth helpers.
- `/app/backend/requirements.txt` zipstream-ng dependency.
- Git status/recent history for uncommitted changes.

## Direct proof required
- Happy path album ZIP and 4-photo selected ZIP return HTTP 200, `application/zip`, and parse as valid archives with expected entries.
- Empty request returns clean JSON 400; unknown album clean JSON 404; oversized DB-seeded selection clean JSON 413.
- Immediately after successful ZIP and after 404/413, `/api/auth/me` and `/api/photos/albums` still return 200 (worker did not die / session intact).
- UI: login as admin, open `/photos`, enter the real album, open PhotoSwipe viewer, confirm displayed image uses `/photos/preview/`, and toolbar Download triggers a browser download.

## Edge cases
- Missing body/selection must not return an empty/malformed response.
- Oversized selection must reject before object storage I/O and must be cleaned from DB.
- UI should surface real server detail instead of generic `Download failed` for server JSON errors.