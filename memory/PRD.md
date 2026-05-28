# Alpha Omega Phi — Product Requirements Document

## Problem Statement
Build a Club-Express-style member-management platform for **Alpha Omega Phi Military Fraternity & Sorority, Inc.** Covering: chapters, member directory, events, news, photos, AOP forms (documents), volunteer hours, awards, donations, gear, reporting, and email communications. Public registration is closed (admin-invite only).

## User Personas
1. **Chapter Admin** — adds/edits members, creates events, manages content, grants awards, reviews hours, runs reports.
2. **Active Member** — RSVPs, logs volunteer hours, views directory, downloads AOP forms, sees birthdays and new members.
3. **Alumni / Lifetime** — same as member; appears in tier filters.

## Architecture
- **Backend**: FastAPI + Motor (async MongoDB), PyJWT + bcrypt, Emergent Object Storage for photos/docs, emergentintegrations for LLM.
- **Frontend**: React 19 + React Router + Tailwind + shadcn/ui + sonner + date-fns + lucide-react.
- **Auth**: httpOnly cookies (24h access / 7d refresh), SameSite=None+Secure.
- **Branding**: Red (#C8102E) / White / Navy (#0A2463). Outfit + Work Sans fonts. 10-yr anniversary countdown widget.

## Implemented

### Foundation (pre-Phase A)
- JWT cookie auth (login/logout/refresh/change-password). Admin and demo seed (idempotent).
- Chapters CRUD, Tiers CRUD, Awards CRUD + grant/revoke, Volunteer Hours (member log + admin review).
- Events + RSVPs, News, CMS Pages, Member directory, Profile + 30-day grace period.
- Photos + AOP Forms via Emergent Object Storage with auth-gated /api/files proxy.
- Admin Dashboard with KPIs + pending inbox.
- Activity Timeline on Profile.
- 10-Year Anniversary Countdown widget on Home.

### Phase A — Schema & UI Expansion (2026-02-27)
- **Chapter** model adds `region` + `state` (legacy school/city still accepted).
- **HoursLogIn** adds `event_type` (aop_related|other), `agency_name`, `host_name`, `host_email`, `host_phone`, `activity`.
- **Award grant** accepts custom `granted_at` date.
- **Member fields** added: `address`, `birthdate`, `branch_of_service`, `member_status` (active|inactive|grace|expired|deceased) via `status_override`.
- New endpoints:
  - `GET /api/members-new?days=N&limit=M` — recently joined members.
  - `GET /api/members-birthdays?days=N&limit=M` — upcoming birthdays (next_birthday, days_until_birthday, age_turning).
  - `PUT /api/members/{id}/status` — admin sets status_override (auto-manages deceased_at).
- **Frontend**:
  - Hours dialog expanded (event_type, agency_name, activity, host name/email/phone).
  - Chapters page + admin dialog use Region & State.
  - Documents page renamed → **AOP Forms** (page + navbar + upload button text).
  - Profile form adds Address + Birthdate inputs.
  - Directory: clickable member card → full profile modal (no security info).
  - Admin Members table: Status column + status pill + **View** Member-Card dialog with full details.
  - Admin New Member + Edit Member dialogs include address, birthdate, branch_of_service, member_status.
  - Award grant dialog includes Date-granted picker.
  - Home page: two columns rendered (logged-in users only) — New Members (last 30d) and Upcoming Birthdays (next 30d).

### Phase B — Omega, Gear, Donations, Calendar, Check-In, Reports (2026-02-27)
- **Omega Chapter** page (`/omega`): in-memoriam grid of members with `status=deceased`. Endpoint `GET /api/omega`.
- **AOP Gear store** (`/gear`): public catalog. Admin CRUD via `GET/POST/PUT/DELETE /api/gear`. Detail dialog with sizes/colors/quantity.
- **Donations & Causes** (`/donations`): public listing of active causes with progress bars; admin CRUD via `/api/causes`; pledge endpoint `/api/causes/{id}/pledge`; aggregation helper `recompute_cause_totals()` runs on PayPal capture.
- **Event Calendar** (`/calendar`): month-grid + agenda list, `GET /api/calendar/events?month=YYYY-MM` (route renamed from `/events/calendar` to avoid shadowing by `/events/{id}`).
- **Event Check-In** on `/events/{id}` (admin only): ticket types (vip/general/guest/speaker/volunteer); endpoints `POST/GET/DELETE /api/events/{id}/check-ins`; duplicate prevention; guest walk-ins supported.
- **Reporting** (Admin → Reports tab):
  - `GET /api/reports/members` with filters status/chapter/tier/role + CSV export.
  - `GET /api/reports/hours` with filters status/event_type/from_date/to_date + CSV export.
  - `GET /api/reports/donations` with cause/status filters + CSV export.
  - `GET /api/reports/personnel-brief/{user_id}` returns full dossier (identity, chapter/tier, awards, hours, events, check-ins, transactions, totals) — printable.
- Seeded sample data: 4 gear items, 3 causes (idempotent).

### Phase C — PayPal LIVE + Resend Email (2026-02-27)
- **PayPal Orders API v2 (LIVE)** server-side checkout (`@paypal/react-paypal-js` on frontend, FastAPI REST via `httpx` on backend):
  - `GET /api/payments/paypal/client-id` — public config.
  - `POST /api/payments/paypal/orders` — create order (donation / gear / event / dues), persists pending transaction with `paypal_order_id`.
  - `POST /api/payments/paypal/orders/{order_id}/capture` — capture & side-effects (donation: recompute cause totals; dues: extend membership +365d).
  - Reusable `<PayPalCheckout />` component wired into Donations (causes), Gear (qty × price), and Profile (annual dues $60).
  - Token caching with TTL.
- **Resend email blasts**:
  - Template CRUD: `GET/POST/PUT/DELETE /api/email/templates`.
  - `POST /api/email/preview` — render with variable substitution + recipient count for chosen segment.
  - `POST /api/email/blast` — send to segment (active/all/admins/tier/chapter/custom) with `test_only` flag; failures logged per-recipient.
  - `GET /api/email/blasts` — history with sent/failed/opens counters.
  - `POST /api/email/webhook` — increments opens/deliveries/bounces by `blast_id` tag.
  - Variable substitution is HTML-escaped (XSS-safe).
  - Frontend Admin → Email tab (Compose / Templates / History) with live preview pane.

### Phase D — Chat (real-time messaging + file sharing) (2026-02-28)
- **Members-only gating**: All routes except `/login` and CMS pages now require auth via `ProtectedRoute`; navbar links hidden when logged out (only logo, 10-year badge, and login button visible); `/` redirects unauthenticated visitors to `/login`.
- **Login page text** updated to "This is for Alpha Omega Phi members only. Once you complete Intake, you will be given access."
- **Home theme** rebuilt to show hero images IN FULL (`object-contain` on navy background, headline below the image — no crop, no overlay).
- **Real-time chat** (`/chat`):
  - Conversations: 1:1 DMs (idempotent — re-using existing DM if one already exists between the two users) + group chats with N members and optional name.
  - Messages: text + multi-attachment with reply quoting, soft-delete, read-receipts, day grouping in UI.
  - File uploads up to **100 MB** per attachment (images render inline, video/audio players inline, files as downloadable cards). Stored in Emergent Object Storage under `chat/{user_id}/{file_id}/{filename}`, registered in `db.chat_files` so `/api/files/{path}` resolves them.
  - WebSocket at `wss://.../api/ws/chat` (cookie-auth using existing access_token JWT); auto-reconnect with 3s backoff; server pushes `message:new`, `conversation:created`, `conversation:updated`, `conversation:deleted`.
  - Settings dialog per conversation: rename group, view members, leave (groups), delete (creator/admin).
- New endpoints: `GET/POST /api/conversations`, `GET/PUT/DELETE /api/conversations/{id}`, `POST /api/conversations/{id}/leave`, `POST /api/conversations/{id}/read`, `GET/POST /api/conversations/{id}/messages`, `DELETE /api/messages/{id}`, `POST /api/chat/upload`, `WS /api/ws/chat`.
- `/api/files/{path}` resolver extended to include `db.chat_files`.

### Phase E — Rich email editor + Signatures + Fixed chapters (2026-02-28)
- **Canonical AOP chapters** (Texas, Florida, Tri-South, DMV) enforced via `reconcile_chapters()` on backend startup. The Admin → Chapters dialog now uses a `Select` locked to these four names. All member-facing chapter pickers (Admin → Members inline dropdown, New-member dialog, Edit-member dialog, /profile) filter by `OFFICIAL_CHAPTER_NAMES` so legacy chapters are hidden — but remain visible in the Admin → Chapters tab for manual cleanup.
- **WYSIWYG email composer** via TipTap (`/app/frontend/src/components/RichEditor.jsx`) — toolbar with bold/italic/strike/H2/quote/bullet/ordered/align/link/image/undo/redo, native paragraph breaks on Enter, inline images via file-picker / drag-and-drop / clipboard paste. Replaces the raw HTML textarea in the Compose tab AND in the Template editor.
- **Email signatures** (personal + shared):
  - `GET/POST/PUT/DELETE /api/email/signatures` — personal sigs are owned by the creating admin; org sigs are visible to every admin.
  - New "Signatures" sub-tab under Admin → Email with two grids (My / Shared).
  - Compose tab has a new "Insert signature" dropdown that appends the chosen sig's HTML to the body.
- **Inline image upload** for emails: `POST /api/email/upload-image` (admin-only, 25 MB cap, jpg/png/gif/webp, registered in `db.chat_files` so the existing `/api/files/{path}` resolver serves them).

### Test Status (iteration_6)
- Backend Phase E: 12/12 pytest pass (`/app/backend/tests/test_phase_e.py`).
- Frontend Phase E: 13/13 asks verified — rich editor toolbar visible, inline image insertion via file-picker confirmed working, signatures CRUD verified, chapter pickers correctly limited to the 4 official chapters across Admin/Members/Profile.

### Known limitations / config items
- **Resend free tier**: `RESEND_FROM=onboarding@resend.dev` only allows sending to the Resend account-owner email until a domain is verified at `resend.com/domains`. The blast endpoint logs the failure reason per recipient — UI shows sent/failed counts. **Action for user**: verify your domain at resend.com and update `RESEND_FROM` in `/app/backend/.env`.
- **Resend webhook**: endpoint exists at `POST /api/email/webhook`. **Action for user**: configure this URL at resend.com/webhooks (use the deployed `*.emergent.host` URL, not preview). Signature verification not yet added.
- **PayPal**: LIVE mode is active. Test orders persist in `transactions` collection as pending until a real buyer approves & capture is called. No real money moves until capture.

## Backlog

### P0 — Production polish
- Resend domain verification + update `RESEND_FROM` env to verified address.
- Register Resend webhook URL in dashboard.
- Add Resend webhook signature verification (svix).

### P1 — Refactor & polish
- Split `server.py` (~2900 lines) into `/backend/routes/` + `/backend/models/` + `/backend/services/`.
- Replace native date inputs with shadcn DatePicker for consistency.
- Email blast: batch with `asyncio.gather` (chunks of 25) once segments grow beyond 100.
- Navbar grows crowded at 11 links — group less-used into a "More" dropdown on wide screens.
- `/api/members-birthdays` aggregation pipeline (scale > 1000 members).

### P2 — Future
- Stripe integration (currently PayPal-only per user choice).
- Member-facing transactions history page (lists past PayPal captures).
- Personnel Brief PDF export (currently browser print).
- Recurring monthly donations / membership auto-renewal.

## Credentials
See `/app/memory/test_credentials.md`.
