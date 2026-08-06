# Auth Testing Checklist (generated for photo-download resilience bug)

- Read `/app/memory/test_credentials.md` and use the admin account.
- Login through `/api/auth/login`; verify it returns a user plus access/refresh tokens and sets cookies.
- Verify authenticated identity with `/api/auth/me` using cookies/Bearer token.
- After the affected endpoint is exercised (success and error paths), call `/api/auth/me` again immediately to confirm the worker/session still responds.
- If login/session fails, inspect backend logs and auth implementation before declaring the photo-download fix verified.