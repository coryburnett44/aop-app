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

### Test Status (iteration_3)
- Backend: 100% on Phase A scope (9/9 in `tests/test_phase_a.py`); 48/50 overall (2 pre-existing file-proxy 401s out of Phase A scope).
- Frontend: 100% on Phase A scope (all UI elements/integrations verified).

## Backlog

### P0 — Phase B (next)
- **Omega Chapter tab**: members with status=deceased — memorial wall with photos, branch, dates.
- **Donations tab**: list active causes, donor history; admin can create causes.
- **AOP Gear store**: admin-editable catalog (items + photos + sizes); member browse.
- **Reporting**: filter members/hours/events/status/dues; export CSV; **Personnel Brief** printable per member.
- **Event Calendar** (full month view) + **Event Check-In** (VIP / Gen Admin track).

### P1 — Phase C (integrations)
- **Stripe + PayPal** payments (dues / events / gear / donations) — needs keys (USER-provided).
- **Resend email blasts** — templates, segments, image embedding, open tracking — needs Resend API key.

### P2 — Refactor & polish
- Split `server.py` (~2000 lines) into `/backend/routes` + `/backend/models` + `/backend/services`.
- Replace native date inputs with shadcn DatePicker for consistency.
- Validate birthdate format on backend (YYYY-MM-DD).
- `/api/members-birthdays` aggregation pipeline (scale > 1000 members).

## Credentials
See `/app/memory/test_credentials.md`.
