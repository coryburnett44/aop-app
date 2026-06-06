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

### Phase AJ — Iteration 41: Automated Annual Dues Reminders (2026-06-06)

Added a system-managed automated email campaign that emails every active, non-lifetime member at four cadence points around their `membership_expires_at`:

| Stage      | When                       | Email content |
|------------|----------------------------|---------------|
| `before_30`| 30 days before expiration  | Friendly heads-up |
| `before_15`| 15 days before expiration  | Reminder |
| `before_5` | 5 days before expiration   | Final notice |
| `grace_1`  | 1 day AFTER expiration     | 15-day grace warning + $75.00 reactivation fee + contact the National office |

**Implementation:**
- New `kind="dues_reminders"` discriminator on `automated_emails` docs (default = `broadcast`).
- `_send_dues_reminders()` dispatched from the existing `_automated_email_loop` (runs once a minute; campaign cron `0 9 * * *`).
- Per-stage subject + HTML body baked into `_dues_reminder_email_html()` — admins don't edit bodies, only toggle the campaign and tweak the cron schedule.
- Dedupe via `db.dues_reminders_sent` collection (unique index on `(user_id, expires_at, stage)`). When a member pays → `membership_expires_at` advances → new keys → next cycle's reminders fire on the new dates. Already-sent stages for the OLD date are never re-sent. **"If they paid, the emails stop."**
- Excludes lifetime members (`is_lifetime_member=true`), inactive members (`status=inactive`), and accounts without email.
- New `seed_builtin_dues_reminders()` runs at startup (idempotent).
- Frontend `AutomatedEmailsAdmin.jsx`: special-cased dues campaigns to hide body editor / audience / sections and show a "System-managed campaign" info panel with the cadence breakdown.
- Preview endpoint stacks all four stage subject lines + bodies so admins can review wording in one view.

**Verification (iter41)**
- Live sandbox: seeded 4 fake users at offsets +30/+15/+5/−1 → `_send_dues_reminders` sent exactly 4 emails, created 4 dedup rows, second run returned 0 (dedupe). Payment-extension scenario: 30-day reminder fires once, payment extends expiration by 365 days, re-run same day returns 0 sent. Admin UI Edit dialog hides body/audience/sections and disables subject as expected.

### Phase AI — Iteration 40: routes/rsvps.py extraction (2026-06-06)
Continuing the server.py refactor: extracted RSVP creation, paid-event Zeffy approval, admin event-ticket approval, RSVP guest-list editing, `/me/events`, QR ticket emails, and check-in lookup/scan endpoints into a new `/app/backend/routes/rsvps.py` module (~480 lines).

**Moved out of server.py (was lines 487-1003):**
- `_create_rsvp_and_email_ticket` helper (shared by free + paid + admin-approve paths)
- `make_ticket_token`, `decode_ticket_token`, `make_qr_png_b64`, `_ticket_card_html` helpers
- `send_rsvp_ticket_email` (Resend-powered QR ticket emails with EVENTS_INBOX_EMAIL CC)
- `POST /events/{id}/rsvp` (toggle, 402 on paid, 400 on cancelled/umbrella)
- `POST /events/{id}/payment/confirm` (Zeffy receipt → pending tx; trust_zeffy auto-approve)
- `PUT /transactions/{tx_id}/approve-event-ticket` (admin approval → RSVP + ticket email)
- `PUT /events/{id}/rsvp/guests` (in-place guest list edit + re-send tickets)
- `GET /me/events`
- `GET /checkin/lookup/{token}` (no auth required, validated server-side)
- `POST /checkin/scan/{token}` (admin only, idempotent)

Helpers exposed on `routes_rsvps.register.*` so any future back-compat shims can wire to them. `server.py: 6371 → 5895 lines (-476 in iter40; cumulative -1759 since iter32 start).`

#### Verification (iter40)
7/7 backend regression tests PASS (free RSVP toggle, paid-event 402, cancelled 400, guest-list PUT, payment/confirm pending tx, admin approve idempotent, checkin lookup+scan with role enforcement). Frontend Admin → Gear dialog test-ids verified (no collision). Test seed: `/app/backend/tests/test_iteration39_rsvp_extract.py`.

### Phase AH — Iteration 38-39: 5 UI/Admin features (2026-06-05)
1. **Home page CTA reorg** — Anniversary button moved next to "Go to my profile" + "See events" in the hero. Standalone Countdown banner removed from Home (still on /anniversary).
2. **Gear external-link items** — `GearItemIn`/`UpdateIn` + `gear_out` gained `is_external_link: bool`, `external_url: str`, `name_html: str`. Public `/gear` GearCard now renders external-link items the same card size with a "Visit" red pill instead of price; clicking opens the URL in a new tab. Both editors (public Gear.jsx + Admin.jsx legacy) expose an "External link mode" checkbox, URL field, and HTML / Rich title textarea (uses `dangerouslySetInnerHTML` on render — limited tag set per UI hint).
3. **Sub-events for any main event** — `SubEventsPanel` now ALWAYS renders for parent events (no `parent_event_id`) when viewer is an admin, and includes a `+ Create sub-event` button. Inline `SubEventCreateForm` posts to `/api/events` with `parent_event_id` set. Members continue to see the panel only when ≥1 sub-event exists.
4. **Custom page Columns block + sitewide upload-only**: Columns block image URL Input replaced with file upload (`col-card-upload-{idx}` / `col-card-remove-{idx}`); standalone Image block URL Input also replaced with upload-only flow. Avatar URL / Cover image URL fields removed in: Profile (`profile-avatar-upload`), Admin → Edit Member (`em-avatar-upload`), Admin → Event editor's gear cover (`gear-admin-cover-upload` — testid was de-collided from the real event-cover-upload), Admin → Gear page banner (`gear-page-hero-upload`).
5. **Profile download buttons under tabs** — `Download my brief` + `Tax letter` moved out of the header and into a `profile-download-row` directly under `TabsList`, freeing the mobile header.

#### Verification
Iter 38: 7/7 main features PASS in live UI (Playwright). Iter 39 retest: 3/3 medium/low follow-ups (gear-admin-editor fields, testid de-collision, gear page banner upload-only) PASS. No regressions to iter 38 flows.



### Phase AG — Iteration 37: routes/reports.py + Awards admin page multi-grant UI (2026-06-05)

#### routes/reports.py (NEW, 707 lines)
The final large refactor block from server.py. Owns:
- `GET /reports/members`, `GET /reports/rsvps`, `GET /reports/hours`, `GET /reports/hours/summary`, `GET /reports/donations`
- `GET /reports/personnel-brief/{user_id}` (JSON) + `GET /reports/personnel-brief/{user_id}/pdf` (ReportLab PDF, ~373 lines of styled layout: §1-§10 sections + avatar normalization via PIL + http fetch with User-Agent for external avatars)
- Two helpers exposed via register attrs: `personnel_brief_data` and `personnel_brief_pdf_response`

server.py keeps the back-compat shims `_personnel_brief_data` and `_personnel_brief_pdf_response` whose `._impl` pointers get wired post-registration. This keeps the member-self `/me/personnel-brief` + `/me/personnel-brief/pdf` endpoints working without touching the auth surface. Verified: member-self download bytes are byte-identical to admin download.

`_period_to_range` was re-added to server.py (it had been removed with the deletion block) — both `routes/hours.py` and `routes/reports.py` inject it via register kwargs.

**server.py: 7183 → 6350 lines (-833 in iter37; cumulative -1304 since iter32 start, from 7654→6350).** Refactor program complete.

#### Awards admin page (/awards) — multi-grant UI consistency
- `GET /api/awards` now returns BOTH `granted_count` (total grants via `count_documents`) AND `granted_distinct_count` (unique recipients via `distinct('user_id')`).
- Catalog card text: when `total == distinct` → "Granted to N member(s)"; when `total > distinct` → "Granted N times to M member(s)".
- Recent recipients list: each grant row now shows an ordinal pill ("2nd Award", "3rd Award", etc.) when the same member earned the same award more than once (`g.ordinal && g.award_count > 1`). Style matches Profile.jsx Awards tab spec exactly. data-testid `grant-ordinal-{grant_id}`.

#### Verification
29/29 backend pytest cases + frontend live UI checks PASS. PDF size 4.8KB with valid `%PDF` magic. Member→admin byte parity on /me vs /reports brief. Permission gating preserved across all 5 admin reports endpoints (member→403).



### Phase AF — Iteration 36: Multi-grant same award + lock down document uploads (2026-06-05)
- **Multiple grants per award per member** — `POST /api/awards/{award_id}/grant` no longer 400s on duplicate `(award_id, user_id)`. Each new grant gets an `ordinal` field (1, 2, 3, ...). The legacy unique compound index `award_id_1_user_id_1` is dropped on startup and replaced with a non-unique index for lookup performance.
- **/me/awards + /members/{id}/awards** now return each grant with `ordinal` and `award_count` (total grants of this award to this user). Backfilled at read-time for older grants without a stored ordinal.
- **Personnel Brief data** now includes `awards_grouped` (one entry per distinct award_id with `{award_name, count, first_granted_at, last_granted_at, grants[]}`) + `awards_distinct_count` alongside the existing flat `awards` + `awards_count`.
- **Personnel Brief PDF §8** renders ONE row per distinct award using the grouped data — e.g. "Service Star | 2nd Award (× 2) | 2026-04-01". Header changed from "Date Granted" → "Latest Date".
- **Profile Awards tab** now renders ONE card per distinct award with an ordinal pill badge like "3rd Award · × 3". Awards stat card + tab label show the DISTINCT count (Set of `award_id || award_name`), not the raw grant count.
- **Admin floating Personnel Brief §8** matches the same grouped rendering using `awards_grouped` from the backend.
- **Document uploads admin-only** — `POST /api/documents` and `POST /api/documents/bulk` now require `admin_tab_dep("documents")` (members get 403). Frontend Docs & Forms page no longer renders the Upload button for non-admins (line 94 of Documents.jsx: `isAdmin && <UploadDocDialog />` instead of `user && <UploadDocDialog />`). Folder creation was already admin-only.
- **Verification**: 10/10 pytest cases + live UI checks for member 403 on docs upload, Profile shows 1 grouped card with "3rd Award · × 3" badge for a member with 3 grants, admin floating brief renders the grouped row.



### Phase AE — Iteration 35: P0 production data-loss fix + chapter dropdown + auto-clear pending flag (2026-06-05)

#### 🚨 P0 ROOT CAUSE — Production data loss
The user reported that on production (aop-app.org) custom events, custom tiers ("Junior Member"), demo members they deleted, and a Book Bag Giveaway album's photos all kept disappearing after redeploys. **RCA**: three startup reconciliation functions used a destructive "delete anything not in canonical allowlist" pattern:
- `reconcile_tiers()` called `db.tiers.delete_one()` for every tier whose name wasn't in `AOP_TIER_NAMES`
- `seed_anniversary_subevents()` had a "Wipe ALL non-anniversary events on startup" block that deleted every event not in the 10-Year-Anniversary canonical tree, **cascading to db.rsvps + db.checkins** (which is also why album photos linked to those events were lost)
- `reconcile_awards()` deleted any non-canonical award AND `db.award_grants.delete_many({award_id})`
- `seed_data()` re-inserted 5 demo members (Riley Chen, Maya Patel, Jordan Reed, Sam Okafor, Harper Liu) whenever they were missing — so admin deletions reverted on every restart

Every prod redeploy = startup = full wipe of admin-created content. **Fix**: all 4 destructive blocks removed; `seed_data` + `seed_phase_b` now gated by a one-time `site_settings.demo_seed_completed` marker so deleted demo data stays deleted forever (marker has been set in preview).

#### Other fixes
- **Edit Member chapter dropdown** now shows ALL chapters from `/api/chapters` (same as `/profile`), not just the Texas/Florida/Tri-South/DMV official subset. Fix applied to 4 admin dropdowns: EditMemberDialog (`em-chapter`), NewMemberDialog (`nm-chapter`), inline member-row (`member-{id}-chapter`), Email blast chapter segment. `BulkImportMembersDialog` intentionally still uses `officialOnly` (CSV import maps to canonical names).
- **Auto-clear pending_set_password on successful login** — `routes/auth.py /auth/login` now flips `pending_set_password=False` after successful password verification. This unblocks members who reset their password via `/reset-password` (or had it changed manually by an admin) so they don't stay flagged forever.

#### Verification
12/12 backend curl checks across `/app/tests/test_iter35_data_persistence.sh` + `/app/tests/test_iter35_part2.sh` — including actual `sudo supervisorctl restart backend` cycle to simulate a production redeploy. Custom tier `Iter35_Junior_*`, custom event `Iter35_EventV2_*`, custom award `Iter35_Award_*`, and deleted demo Sam Okafor all survive the restart. F5 verified live in Playwright: 'National' chapter visible in `em-chapter` dropdown alongside DMV/Florida/Texas/Tri-South.

#### Deferred
- `routes/reports.py` extraction (5 reports + Personnel Brief PDF, ~500 lines) — deferred this session to focus on the data-loss emergency.
- `/api/members?q=` search filters by name only, not email. Worth confirming with the user separately whether to extend.



### Phase AD — Iteration 34: Bulk resend set-password + routes/applications.py + routes/hours.py (2026-06-05)
- **Bulk resend set-password** — New backend endpoint `POST /api/admin/members/bulk-resend-set-password` (admin-only, members tab). Iterates over every user flagged `pending_set_password=true`, invalidates older unused tokens (`used=true, invalidated_by='bulk-resend'`), mints fresh 7-day tokens, and sends the welcome email via Resend. Returns `{ok, total, sent, failed, skipped_no_email, members:[{id, name, email, sent, skipped?, error?}]}`. 503 when RESEND_API_KEY missing. Frontend: Admin → Members toolbar now renders both pills together when pending users exist — `filter-pending-setpw` (toggle pending-only view) and `bulk-resend-setpw` (solid amber "Resend to all N"). Helper `bulkResendSetPassword()` confirms via `window.confirm`, posts, distinguishes full-success vs partial via `toast.success`/`toast.warning`, refreshes list.
- **routes/applications.py (NEW, 304 lines)** — `POST /auth/apply`, `GET /admin/applications`, `POST /admin/applications/{id}/review`, plus all 3 Resend email templates (admin notification, approval welcome, rejection) extracted. The approval flow correctly reuses the applicant's chosen password from the application doc — verified end-to-end via live login post-approval.
- **routes/hours.py (NEW, 197 lines)** — `POST /hours`, `GET /hours`, `PUT /hours/{id}/review`, `DELETE /hours/{id}`, `GET /me/hours`, `GET /me/hours/summary` extracted. `hours_out` serializer and `_period_to_range` helper stay in server.py and are injected. Chapter-scoping for Governor Manager still works via injected `is_chapter_scoped` / `chapter_scope_user_ids`.
- **server.py: 7447 → 7103 lines (-344 in this iteration; cumulative -551 since iter32 session start, 7654→7103)**. Pattern is now reproducible — applications + hours + auth_email_flows + events + members all use the same `register(api, **deps)` factory.
- **Deferred**: `/events/{id}/rsvp` + `/events/{id}/payment/confirm` + `/transactions/{id}/approve-event-ticket` + `/checkin/*` (heavy PayPal/Zeffy/JWT-ticket coupling) and `/reports/*` + Personnel Brief PDF (heavy ReportLab dependencies). Both blocks remain in server.py for now and would each warrant a dedicated iteration.
- **Test coverage**: 19/19 new tests + 25/25 iter33 + 6/6 iter32 regression = **50/50 passing**. Frontend live-verified: both amber pills render, `bulk-resend-setpw` POST → 200 → all members sent.



### Phase AC — Iteration 33: Refactor phase 4 (events.py, members.py, auth_email_flows.py) + Pending password setup badge (2026-06-05)
- **routes/auth_email_flows.py (NEW, 162 lines)** — 4 endpoints extracted: `POST /auth/set-password`, `POST /auth/forgot-password`, `POST /auth/reset-password`, `POST /auth/change-password`. Both email-template helpers (`_send_set_password_email`, `_send_password_reset_email`) moved into the module and exported via `register.send_set_password_email` / `send_password_reset_email`. server.py keeps a thin `_send_set_password_email(email, name, token)` shim whose `._impl` is wired post-registration so bulk-import + apply-approval + the new resend endpoint keep working.
- **routes/events.py (NEW, 97 lines)** — 7 endpoints extracted: list/get/create/update/delete events, list sub-events, list rsvps. `event_out` stays in server.py (used by many other endpoints) and is injected via register kwargs. The RSVP-create / PayPal-capture / check-in flows remain in server.py because they cross-cut with Zeffy/PayPal/Resend.
- **routes/members.py (NEW, 107 lines)** — 5 endpoints extracted: list members (with q+city filters), get member, /members-new, /members-birthdays (incl. Feb 29 next-birthday logic), PUT /members/{id}/status. Admin CRUD (POST /admin/members, PUT /members/{id}, DELETE, /role, /tier, /chapter, /bulk-import, /pending-intake-changes) intentionally remain in server.py because they cross-cut PayPal renewal, tier reconciliation, cascade deletes, and welcome-email side effects.
- **server.py: 7654 → 7447 lines (-207 net).** Cumulative refactor since Phase T: 7079 → 7447 (the difference is offset by all the new features that landed between T and Z — gear redesign, Zeffy flow, chat TTL, member CSV import, Personnel Brief PDF, Profile expansion). Net post-feature-growth the monolith is back below the 7500 line "creep" threshold and the pattern is fully established.
- **Pending password setup badge + Resend link** — `user.pending_set_password: bool` now surfaced in `public_user`. New backend endpoint `POST /api/admin/members/{id}/resend-set-password` (admin-only, members tab) invalidates older unused tokens, creates a fresh 7-day token, sets `pending_set_password=true`, and emails the link via the extracted Resend helper. Frontend Admin → Members table now shows: (1) an amber `Pending password setup` pill (`data-testid pending-setpw-{id}`) next to the name; (2) a `Resend link` outlined button (`data-testid resend-setpw-{id}`) in the actions column; (3) a toolbar filter button `<N> pending password setup` (`data-testid filter-pending-setpw`) that toggles a pending-only view.
- **Test coverage**: 25/25 backend pytest in `/app/backend/tests/test_iteration33_refactor_pendingsetpw.py` + 16/16 phase_o regression pass. Frontend Playwright verified: filter button shrinks table to pending-only and back; badges + resend buttons render correctly on the pending users.



### Phase AB — Iteration 32: Set-password page restored + Login-lockout bypass for correct creds + Custom admin-tab permissions (2026-06-05)
- **Set-password page brought back** — `/app/frontend/src/pages/SetPassword.jsx` (mirrors ResetPassword.jsx). App.js route changed from `<Navigate to="/login">` to `<SetPassword />`. New bulk-imported members now land on the actual password-set form when clicking the email link, then redirect to /login. Backend `/auth/set-password` endpoint was already in place — just the frontend was the regression.
- **Login lockout no longer blocks correct credentials** — `routes/auth.py /auth/login` now verifies the password FIRST. On success: counter cleared, user logged in (no more "Too many attempts" for legitimate users). On failure: existing 5-attempt soft-lock (15-min) still applies and increments. Error message clarified to "Too many incorrect attempts. Try again in 15 minutes."
- **Custom per-admin tab permissions** — Full Admins can now grant any admin user a custom set of admin-console tabs that overrides their `admin_role` defaults.
  - Backend: `user.allowed_tabs: List[str]` field (admin-only, persisted). `ALL_ADMIN_TABS` set + `effective_admin_tabs(user)` helper (custom list takes priority over `ADMIN_ROLE_TABS[role]`). `admin_can` reads through `effective_admin_tabs`.
  - `GET /admin/permissions` returns `all_tabs` (14 canonical keys), `role_default_tabs` (per-role default), `has_custom_tabs` (bool).
  - `PUT /api/members/{id}` accepts `allowed_tabs: List[str]`; sanitized against `ALL_ADMIN_TABS`; empty list clears the override. Gated to full admins (non-full → 403). Downgrading a user role→member auto-clears admin_role + allowed_tabs.
  - Frontend: `AdminTabPermissionsEditor` component (in `Admin.jsx`) renders inside `EditMemberDialog` when role=admin. 14 checkboxes (3-col grid), data-testid `em-tab-perm-<tab>`, `em-tab-perms`, `em-tab-perms-reset`. Dashboard checkbox always required (disabled+checked). Reset link visible only when an override is currently set. Whole editor disabled for non-full admins.
- **Test coverage**: 6/6 backend pytest in `/app/backend/tests/test_iteration32_setpw_lockout_tabs.py` + frontend Playwright UI verification of SetPassword page render + EditMemberDialog tab-perms grid + grant/revoke/gate end-to-end. No regressions.



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

### Phase Z — Chat TTL/emoji picker tablet cutoff fix + Zeffy auto-approve for trusted members (2026-06-03)
- **REAL ROOT CAUSE OF CHAT TTL CUTOFF FOUND** — Phase W had partially fixed mobile but **tablet was still broken**. The picker used `sm:right-0 sm:absolute` which anchored to the parent (the tiny TTL button's `relative` wrapper). At tablet 768x1024 the picker rendered at x=-102 (102px off-screen left) because the 260px-wide picker extended beyond the button's right edge. **Fix**: use a single positioning class for all viewports — `fixed bottom-[5.5rem] left-1/2 -translate-x-1/2 w-[min(280px,calc(100vw-1.5rem))] z-[60]`. Picker is now viewport-centered above the composer on every device. Same fix applied to the emoji picker. **Verified at 390/768/1440 — all unclipped** (TTL at tablet now x=244, fully inside 768px viewport).
- **Chat settings dialog TTL grid** — changed from `grid-cols-4` to `grid-cols-2 sm:grid-cols-4` so the "1 hour / 24 hours / 7 days" labels don't get squeezed at narrow widths.
- **Zeffy auto-approve for trusted members** — `routes/site_settings` style backend logic in `server.py`:
  - New `ZEFFY_RECEIPT_PATTERNS` tuple: 10+ uppercase alphanumeric, `ZF[-_]?` prefix (case-insensitive), email format. Min 6 chars hard floor.
  - `_is_valid_zeffy_receipt(s)` helper.
  - `POST /api/payments/zeffy/confirm` now: if `user.trust_zeffy=true` AND pattern match → transaction created with `status='completed'`, `approved_by='system:zeffy-trust'`, `zeffy_auto_approved=true`, AND `membership_expires_at` extended 365 days inline. Otherwise → pending (manual admin queue, unchanged).
  - `trust_zeffy: Optional[bool]` added to `AdminUpdateMemberIn`. `user_out` exposes `trust_zeffy: bool`. `tx_out` exposes `zeffy_auto_approved: bool` (testing-agent fix).
- **Admin UI** — `Admin.jsx` Edit Member dialog has a new amber-50 callout with "Auto-approve Zeffy dues payments" checkbox (`em-trust-zeffy`) above the password reset field. Pre-populates from `trust_zeffy`. Stored via existing `PUT /api/members/{id}` flow.
- **Behavior matrix verified**:
  | trust_zeffy | confirmation | result |
  |---|---|---|
  | true | `ZF-ABC123DEF` | ✅ auto-approved + extended |
  | true | `ABCDEFGHIJ` | ✅ auto-approved |
  | true | `user@example.com` | ✅ auto-approved |
  | true | `bad` (3 chars) | ❌ stays pending |
  | true | `12345` (5 chars) | ❌ stays pending |
  | false | `ZF-ABCDEF` | ❌ stays pending |
- **Test coverage**: 13 new tests in `/app/backend/tests/test_phase_z.py` + 15 Phase Y regression — **28/28 passing**. Frontend verified at 390/768/1440 viewports for chat pickers + dialog grid + admin checkbox. Cumulative: **184/184 backend pytest passing** across Phases T–Z.


- **Home page widget** — `/app/frontend/src/components/CommunityServiceLeaderboard.jsx` (~150 lines). Two-tab UI (Top Chapters / Top Members) showing top-5 by approved volunteer hours this quarter. Gold/silver/bronze rank badges, avatars for members, period label "Q2 2026". Fetches `/api/leaderboards/community-service?period=quarter`.
- **Backend** — `/api/leaderboards/community-service` returns `{period_label, top_chapters[5], top_members[5]}` filtered to `status:approved`, supports `period=quarter|year|all`. Joins users → chapters for enrichment. Open to all authenticated members (no admin gate).
- **Home section toggle** `leaderboard` added to `home_sections` defaults + migration. SiteSettingsAdmin shows "Community Service Leader Board" toggle.
- **Zeffy dues integration** — confirmation-on-return pattern (Zeffy has no webhook in free tier):
  - `ZEFFY_DUES_URL` env var (default `https://www.zeffy.com/en-US/ticketing/national-yearly-dues`).
  - `GET /api/payments/zeffy/config` returns `{url, currency:'USD', default_amount:60, enabled:true}`.
  - `POST /api/payments/zeffy/confirm` member submits `{confirmation:'receipt#', amount}` → creates a `pending` transaction with `provider:'zeffy'`, `purpose:'dues'`, `type:'renewal'`.
  - `PUT /api/transactions/{id}/approve-zeffy` admin approves → sets `status:'completed'`, extends `membership_expires_at` by 365 days (mirrors PayPal dues path). Idempotent (`{ok:true, already:true}` if already approved). Returns 400 for non-Zeffy txs.
- **Profile UI** — `/app/frontend/src/components/ZeffyCheckout.jsx` (~115 lines). Side-by-side with PayPal in `dues-checkout-row` grid. Click "Pay dues with Zeffy" → opens Zeffy in new tab + shows "I completed my Zeffy payment" button → opens modal with receipt# input → POST /confirm.
- **Admin approval UI** — `Reports → Dues approvals` tab (`reports-tab-dues`). `ZeffyDuesApprovals` lists pending Zeffy txs with member name + amount + Approve/Reject buttons. Optimistic local removal + load() reconciles.
- **`tx_out` helper** extended (testing-agent fix) to include `provider`, `purpose`, `zeffy_confirmation`, `approved_at`, `approved_by`, `approved_by_name` fields so the frontend admin panel can filter Zeffy txs.
- **CRITICAL FIX** (after testing-agent flagged) — `ZeffyCheckout.openZeffy` no longer passes `noopener,noreferrer` to `window.open` (Chrome/Firefox/Safari return `null` when noopener is set, which made the code think the popup was blocked and navigate the current tab away from /profile). Fix: drop the popup-features arg, always `setOpened(true)` before opening, fall back to clipboard-copy on hard popup-block. Verified end-to-end at 1440×900: tab stays on /profile, popup opens to Zeffy, "I completed my Zeffy payment" button appears.
- **React key warning in HoursReport** — partial fix via `setRows([])` reset on view change (clears stale-shape rows before new fetch). Remaining warning is in shadcn Select internal mapping, non-blocking.
- **Test coverage**: 15 new tests in `/app/backend/tests/test_phase_y.py` — 100% passing after `tx_out` fix. Covers leaderboard shape + ordering + only-approved + period variants; Zeffy config/confirm/approve including idempotency and admin gating; regression on hours summaries. **Cumulative: 156/156 backend pytest passing** since Phase T.


- **Member-side filtering**: `/api/me/hours` now accepts `year`, `quarter` (1-4), `month` (1-12), `status_filter` query params. New `/api/me/hours/summary?year=` returns a structured year rollup `{year, total_approved, total_pending, by_month: [{label:"Jan", key:"2025-01", hours, approved_hours, count}, …], by_quarter: [{label:"Q1", key:"2025-Q1", …}, …]}` — always 12 months / 4 quarters even when empty.
- **`/hours` page** — "My hours" tab adds Year (last 5 years) + Period (Entire year / Q1-Q4 / Jan-Dec) selectors via shadcn `Select`. URLSearchParams-built query refetches on change. Stack-vertical on mobile, side-by-side on `sm:` and up. Empty-state copy now reads "No hours in this period — adjust the year/period filters, or log new hours."
- **Admin reports**: `/api/reports/hours` extended with `year`, `quarter`, `month`, `chapter_id` filters (composable with existing `status_filter`, `event_type`, `from_date`, `to_date`, `user_id`). **NEW** `/api/reports/hours/summary` returns aggregated rows + totals:
  - `group_by=member` → `[{user_id, user_name, chapter_id, chapter_name, hours, count}, …]` sorted by hours desc.
  - `group_by=chapter` → `[{chapter_id, chapter_name, hours, count, member_count}, …]` with "Unassigned" bucket for chapter-less members.
  - `group_by=overall` → single `[{label:"All hours", hours, count}]` row.
  - `group_by=month` | `quarter` | `year` → auto-bucketed periods with `period_key` ascending.
  - `totals: {approved_hours, pending_hours, rejected_hours, approved_count, pending_count, rejected_count}` for the filter window.
- **Reports → Hours UI** — full redesign: 5 filter selects (Year, Period, Chapter, Status, Event type) + 4 view tabs (Individual entries / By member / By chapter / By period). Totals dashboard card. CSV export adapts headers per view (e.g. By chapter exports Chapter/Approved hours/Entries/Active members). All 4 views verified at 1440×900.
- **Helper**: `_period_to_range(year, quarter, month)` converts year/quarter/month to ISO Z-suffixed date range using `calendar.monthrange` for last-day-of-month correctness. Quarter takes precedence over month if both passed.
- **Chapter scoping**: `governor_manager` admin sees only their assigned-chapter members in both `/reports/hours` and `/reports/hours/summary` — verified by intersecting `user_id` filter sets.
- **Test coverage**: 27 new tests in `/app/backend/tests/test_phase_x.py` — 100% passing. Covers period filters, year rollup default-year math, all 6 `group_by` variants, chapter scoping, admin gating (member 403), and regression on `/api/hours` queue + `PUT /api/hours/{id}/review`. Cumulative: **141/141 backend tests passing** since phase T.
- **Cleanup carried**: removed the older `/me/hours` route definition (was at line 1874) that did not support filtering; the new filter-aware version at line ~4430 is the only one in the router now.


- **Email-or-username login**: `/api/auth/login` now branches on `@` presence — emails take the existing exact lookup, usernames use case-insensitive regex match (`{"username": {"$regex": ..., "$options": "i"}}`). `LoginIn.email` field changed from `EmailStr` to `str` (back-compat with existing clients). Error message updated to "Invalid email/username or password". `Login.jsx` label is now "Email or username", `type="text"`, `autocomplete="username"`, placeholder "you@example.com or your username". Verified with admin's username `clubadmin` and case-variants (`CLUBADMIN`).
- **URL validation** for image fields — `routes/site_settings.py` adds `_validate_url_field()` that accepts `http(s)://…`, `/relative/path`, or empty string; rejects free-text like "not a url" with a 422 Pydantic error "Must be a full URL (https://…) or a /path/to/file". Applied to `LeadershipItemIn.image_url` and new `FounderItemIn.image_url` via `@field_validator`. Lenient enough for our own `/api/files/…` upload paths to work.
- **Founders strip is now fully admin-editable** — new `/app/frontend/src/components/FoundersAdmin.jsx` (~160 lines, mirror of LeadershipTeamAdmin). Admin → Pages → Site copy → "Founders strip (homepage)" lets admins edit eyebrow + title, add/remove/reorder founder portraits with display name, role/title, and image upload via new `POST /api/founders/upload-image`. `Home.jsx` removed the hardcoded `FOUNDERS` array — section reads `settings.founders_items` and the grid is responsive (mobile 2 cols / sm+ 1×N cols based on item count, capped at 4 wide).
- **Cover-photo URL inputs eliminated** across the admin UI — replaced with upload-only buttons + preview:
  - Event editor (`EventDialog`): now uses `/api/events/upload-cover` (new endpoint). `event-cover-upload` button with preview thumbnail. EventDetail page changed from `aspect-[21/9] object-cover` (crop) to `object-contain max-h-[600px]` so the **entire** cover photo is visible on all viewports (laptops, tablets, phones).
  - News editor (`NewsDialog`): `news-image-upload-btn` upload-only.
  - Cause editor (`CauseDialog` in Donations): `cause-image-upload-btn` upload-only.
  - Gear item editor (`Gear.jsx`): `gear-cover-upload` upload-only.
  - Leadership item editor (`LeadershipTeamAdmin.jsx`): URL input removed; upload-only.
- **Chat TTL (disappearing-messages) picker** — same viewport-safe fix that was applied to the emoji picker: `fixed sm:absolute bottom-20 sm:bottom-12 left-1/2 -translate-x-1/2 sm:left-auto sm:right-0 sm:translate-x-0 z-[60]`. On mobile (≤640px) it floats centered above the composer (no clipping at 390px viewport); on desktop it anchors above the TTL button at the right edge as before.
- **Test coverage**: 26 new tests in `/app/backend/tests/test_phase_w.py` + 88/88 regression from T+U+V = **114/114 cumulative passing**. Frontend Playwright: 13/13 critical flows verified including responsive checks at 390×800 / 768×1024 / 1440×900 viewports.
- **Server.py refactor paused** this session — events/members/auth extractions deferred to keep this large feature batch low-risk. Pattern is fully established (6 modules extracted, 583 lines removed) — next session resumes with `/api/events` (~600 lines).


- **Leadership Team is now fully admin-editable.** New `/app/frontend/src/components/LeadershipTeamAdmin.jsx` (~160 lines) renders inside Admin → Pages → Site copy. Admins can: edit the section eyebrow + title, add/remove leadership terms, reorder via up/down arrows, set each term's display name + alt text + banner image URL or upload via `/api/leadership/upload-image` (admin-only, returns `{url}` after writing to object storage). Home.jsx no longer has a hardcoded `LEADERSHIP` array — it reads `settings.leadership_team_items` and conditionally renders the section only when `length > 0`. Grid is dynamic: `md:grid-cols-2` for 2 items, `lg:grid-cols-3` for 3+.
- **Backend support** — `routes/site_settings.py` adds `LeadershipItemIn` (term/image_url/alt with `Field(max_length=…)` constraints), plus `leadership_team_title`, `leadership_team_eyebrow`, `leadership_team_items` to `SiteSettingsIn` (max 10 items). `make_default_settings` seeds the existing 2024-2026 and 2026-2028 banners so the section appears on first load. `_ensure_site_settings` migration backfills these on existing docs (idempotent — verified across multiple GETs).
- **New upload endpoint** `/api/leadership/upload-image` in `server.py` (gated by `admin_tab_dep("pages")`, reuses the existing `_upload_image` helper that writes to object storage). Returns `{url}` for the frontend to drop into `leadership_team_items[idx].image_url` before saving.
- **Server.py refactor phase 3** — extracted 3 more route modules using the same `register(api, **deps)` factory:
  - `/app/backend/routes/news.py` (56 lines) — `/api/news` GET list/get + admin CRUD.
  - `/app/backend/routes/chapters.py` (69 lines) — `/api/chapters` CRUD with `with_chapter_counts` helper that joins live `db.users` counts. Duplicate-name returns 400.
  - `/app/backend/routes/tiers.py` (53 lines) — `/api/tiers` CRUD with per-tier `member_count` join.
  - `chapter_out` and `tier_out` re-exported from server.py for back-compat with any in-file callers that still construct chapter/tier payloads inline (verified: members admin uses these helpers).
- **server.py: 6786 → 6496 lines** (-290 in this phase). Cumulative refactor since phase T: **7079 → 6496 (-583 lines, -8.2%)**. Foundation is solid: pattern is now copy-paste for the remaining big modules (events ~600 lines, members ~600 lines, auth ~400 lines).
- **Test coverage**: 34 new tests in `/app/backend/tests/test_phase_v.py` + 30 regression in Phase U + 24 in Phase T = **88/88 backend pytest passing**. Frontend Playwright E2E: 7/7 steps — add term, save, edit, reorder, remove with confirm dialog, /home rendering both seeded items, restoration of seed data via PUT.
- **Reviewer notes from testing agent (non-blocking)**: (a) `news_out` lacks `updated_at` — only created_at; (b) `LeadershipItemIn.image_url` lacks `HttpUrl` validation (a typo in URL silently renders broken `<img>` on Home — Pydantic `HttpUrl` would catch it); (c) `governor_manager` and `membership_manager` sub-roles correctly get 403 on `/api/leadership/upload-image` because they don't have "pages" in their allowed tabs. All informational only.


- **Removed secondary banner photo** above the old "Setting the standard, every chapter, every day." headline on Home (per user request).
- **New Leadership Team section** on Home (data-testid `home-leadership`) rendered directly above the family-pulse "Who joined, who's celebrating" block. Two banner images side-by-side on tablet+ (`md:grid-cols-2`), stacked on mobile. Hard-coded for now: `2024-2026` (Kendra Garrett + Brandy Brodie) and `2026-2028` (Sheron Andrews + Tana Blue). Section gated by `showSection("leadership_team")` so admins can toggle it via Admin → Pages → Home page sections.
- **home_sections migration** — `routes/site_settings.py::_ensure_site_settings` now (a) adds `leadership_team: True` to any existing site-settings doc that lacks it, (b) drops the stale `secondary_banner` key. Idempotent — running migration multiple times produces the same end state.
- **`HOME_SECTION_KEYS` update** in `SiteSettingsAdmin.jsx` — replaced `secondary_banner` row with `leadership_team` row (data-testid `home-section-leadership_team`). Admin can ON/OFF the leadership banner section live.
- **Server.py refactor phase 2** — three route modules extracted using a `register(api, **deps)` factory pattern that avoids circular imports:
  - `/app/backend/routes/pages.py` (66 lines) — `/api/pages` CRUD, includes `_validate_blocks` against `PAGE_BLOCK_TYPES`.
  - `/app/backend/routes/site_settings.py` (105 lines) — `/api/site-settings` GET/PUT, owns `SiteSettingsIn`, `make_default_settings()`, and `_ensure_site_settings()`.
  - `/app/backend/routes/ai.py` (51 lines) — `/api/ai/event-description` + `/api/ai/draft-email` + `run_claude` helper.
  - server.py mounts via `routes_pages.register(api, db=db, admin_tab_dep=admin_tab_dep, iso=iso, now_utc=now_utc)` immediately before `app.include_router(api)`. Back-compat shim `_ensure_site_settings = routes_site_settings.register.ensure` keeps any in-file callers working.
  - **server.py: 6786 → 6626 lines** (-160). Cumulative: 7079 → 6626 (-453 since phase T started).
- **Test coverage**: 30 new tests in `/app/backend/tests/test_phase_u.py` + 24 regression in `test_phase_t.py` = **54/54 passing**. Phase U covers: leadership_team migration, /pages CRUD via extracted route, /site-settings extracted route, /ai admin-gating, plus regression on /auth/login, /auth/me, /auth/refresh, /events, /members, /chapters, /tiers, /automated-emails. Frontend verified in live preview (1440×900 + 390×800 viewports) — DOM ordering, toggle on/off, mobile stacking all confirmed.


- **Models extraction (refactor phase 1)** — Moved all 35 Pydantic models (RegisterIn, ProfileUpdateIn, EventIn, PageIn, …) from `server.py` into `/app/backend/models.py` (367 lines). `server.py` reduced from 7079 → 6768 lines. Imported back via single `from models import (…)` statement. No functional change; backend pytest still passing (24/24 in test_phase_t.py).
- **CMS Page Builder (drag-and-drop)** — new `/app/frontend/src/components/cms/PageBuilder.jsx` powered by `@dnd-kit/sortable`. 10 block types: heading, subheading, paragraph, image, button, divider, html, spacer, columns (2-4 cards each with title/body/image), video (YouTube embed). Each block has an inline editor with live preview. Drag-grip reorders the list; trash icon removes. Block-type names are scoped by `testIdPrefix` to avoid collisions when multiple builders coexist on a page.
- **CMS Block Renderer** — `/app/frontend/src/components/cms/BlockRenderer.jsx` is the public-facing renderer. Used by `CmsPage.jsx` (replaces the old whitespace-pre-wrap body when `blocks.length > 0`) and by Home (for custom top + bottom blocks).
- **Backend `Pages` block support** — `PageIn` / `PageUpdateIn` add `blocks: List[PageBlockIn]`. `create_page` / `update_page` validate every block's `type` against the `PAGE_BLOCK_TYPES` allowlist (heading/subheading/paragraph/image/button/divider/html/spacer/columns/video) — returns 400 otherwise. `page_out` always includes `blocks` (defaults to `[]`). Legacy pages with empty blocks still render via the body field.
- **Home page composition** — `site_settings` extended with: `home_sections` (8-key dict: founders/hero_text/countdown/pillars/family_pulse/secondary_banner/upcoming_events/news — each bool, default true), `home_blocks_top` (custom blocks inserted between hero and countdown), `home_blocks_bottom` (custom blocks rendered after News). `Home.jsx` reads section toggles + renders top/bottom blocks via `<BlocksRenderer/>`. Admin → Pages tab now shows: site copy → 8 ON/OFF toggle cards in a 2-col grid → "Custom blocks — top of home" drag-drop builder → "Custom blocks — bottom of home" drag-drop builder → per-page H1/nav-label overrides. `_ensure_site_settings()` migrates the existing doc by `$set`ing any missing default keys (so the new fields appear without manual migration).
- **Backend security** — `update_site_settings` mirrors the block-type allowlist check for `home_blocks_top` and `home_blocks_bottom` (400 on invalid type, e.g. `{"type":"HACK"}`).
- **Updated 4 founder portraits** on `Home.jsx` (FOUNDERS array) — Christian Burnett, Cory Burnett, Dr. Ken Thompson, Lekita Cox-Thompson. Photo grid switched from `aspect-[3/4] object-cover` (cropped heads) to `aspect-square object-contain` (full portraits visible). Removed the burned-in gradient overlay since each image already has the name + branch baked in. Layout: 2x2 on mobile, 4x1 on tablet+ — responsive.
- **Chat emoji picker viewport-safety** — `Chat.jsx` emoji popover changed from `absolute bottom-12 left-0` to `fixed sm:absolute bottom-20 sm:bottom-12 left-1/2 -translate-x-1/2 sm:left-0 sm:translate-x-0 z-[60]`. On mobile (≤640px), it floats centered above the composer (35px from left edge at 390px viewport — verified by testing agent — no overflow). On desktop, it anchors to the emoji button as before. Higher z-index (60) prevents clipping behind chat header / dialog overlays.
- **Photo downloads** — Verified already present from previous phases: single-photo download via per-tile `Download` button (`PhotoTile.downloadOne` streams the blob), multi-select via `setSelectMode` + `downloadSelected` (ZIP of selected ids), full-album ZIP via `downloadAlbum`. Backend endpoint `/api/photos/download-zip` (POST {album} or {photo_ids: []}) — ZIP streamed via `StreamingResponse`.
- **Test coverage**: 24/24 backend pytest in `/app/backend/tests/test_phase_t.py` covering CMS pages CRUD with blocks, all 10 block types, invalid block rejection, site_settings home_sections + home_blocks save/persist/restore, member 401/403 on PUT, regression smoke on /events /members /chapters /tiers /automated-emails. Frontend Playwright iteration 19 confirmed: hero-founders renders 4 portraits, all 8 home-section-* toggles save+toggle the sections live, emoji picker stays inside viewport on both desktop and 390px mobile. End-to-end UI New-page → blocks → save → /page/<slug> render verified by main-agent self-test (Card 1/2/3 columns block visible).


- **TTL index on `password_reset_tokens`** — stored a BSON Date `expires_at_dt` alongside the ISO string field; created index `expireAfterSeconds=60`. MongoDB auto-deletes expired reset tokens within ~1 minute of expiry — no more table bloat.
- **Token-version invalidation** — `User.token_version` (defaults to 0). JWT access + refresh tokens now carry `tv` claim. `get_current_user` rejects any token whose `tv < user.token_version` with `401 "Session expired — please sign in again."`. `/auth/reset-password` increments `token_version`, so **every active session of that user is instantly killed** when they reset their password. Refresh flow re-checks `tv` too. Verified end-to-end with a throwaway user: register → token works → reset password → same token now 401 → fresh login issues new token with `tv=1` and works again.
- **Automated email campaigns** — new admin feature at `Admin → Email → Automated`:
  - Built-in `Weekly Digest` campaign auto-seeded on startup. Cron `0 9 * * 1` (Mondays 9am UTC), audience `all`, all sections enabled. Built-in is editable (subject, body, cron, audience, sections, active toggle) but NOT deletable.
  - Admins can create their own campaigns via `POST /api/automated-emails` with: `name`, `subject`, `body_html`, `cron_expression`, `is_active`, `audience{type:'all'|'chapter'|'tier'|'status', ids:[]}`, `sections{events,photos,documents,new_members,my_rsvps,pending_hours,birthday_greeting}`. Invalid cron → 400 with helpful message.
  - **Merge tags** — `{{member_name}}`, `{{upcoming_events}}`, `{{new_photos}}`, `{{new_documents}}`, `{{new_members}}`, `{{my_rsvps}}`, `{{pending_hours}}` (admin recipients only), `{{birthday_greeting}}`. `_render_automated_body` substitutes each into rendered HTML cards per recipient. Subject also supports `{{member_name}}` via `_render_subject` helper.
  - **Background loop** — `_automated_email_loop` ticks every 60s, finds campaigns whose `next_run_at <= now`, sends to audience, recomputes `next_run_at` from cron. Sender uses existing `RESEND_FROM` (info@aop-app.org).
  - **Run-now** — `POST /api/automated-emails/{id}/run-now` triggers an immediate send to the full audience and returns `{sent: N}` count.
  - **Preview** — `POST /api/automated-emails/{id}/preview` renders the email as it would arrive in the calling admin's inbox (with their merge data applied to both subject and body).
- **UI**: full editor dialog with cron-preset dropdown (`data-testid='cron-preset'`), insert-merge-tag pill buttons, audience type selector + checkbox list of chapters/tiers/statuses, section toggle checkboxes, active toggle, preview iframe. Each campaign row has run-now, edit, delete, and active-toggle controls.
- **Test coverage**: 16/16 backend pytest pass after subject-merge-tag fix (`/app/backend/tests/test_phase_o.py`); UI verified by testing agent iteration 18 + manual `curl preview` confirmation that subject now substitutes correctly.
- **Minor testid additions**: `data-testid='cron-preset'` on cron preset Select, `data-testid='conversation-row-{id}'` on chat conversation list rows.

### Phase R — 9-feature mega-batch (Photos cover+category, Chat emoji/reply/disappearing, Forgot password, Multi-doc upload, Doc folders, Members filter, Hours enrichment, Cascade delete, MacBook Safari fixes) (2026-06-03)
- **Photo albums**: each album now has `category` (auto-detected from name — anniversary / ceremony / conference / tournament / line / community / other) and `cover_url`. Frontend shows category pills filter on the album grid; admin or album creator can edit category via gear icon. Inside an album, hover any photo → click ⭐ to set it as the cover (`PUT /api/photos/albums/{id}` with `cover_photo_id`). When no cover is set, the first uploaded photo auto-becomes the cover preview.
- **Chat emojis**: 78-emoji picker organized in 5 categories (Smileys/Gestures/Hearts/Celebration/Symbols) — click inserts at caret in textarea.
- **Chat reply**: hover any message → reply icon → composer shows a reply-preview banner with sender name + excerpt → backend stores `reply_to` → bubble renders an inline blockquote pointing at the parent message.
- **Chat disappearing messages**: per-conversation default (`PUT /api/conversations/{id}` `{ttl: 'off'|'1h'|'24h'|'7d'}`) + per-message override (composer alarm-clock icon). Backend stamps `first_read_at` only when the FIRST non-sender recipient calls `POST /conversations/{id}/read`. `list_messages` filters out messages where `now - first_read_at >= ttl_seconds`; expired messages are also soft-deleted in DB to keep the collection lean.
- **Forgot password flow**: new pages `/forgot-password` and `/reset-password?token=…`. Backend `POST /auth/forgot-password` is enumeration-safe (always 200), generates a 1-hour token, emails a Resend link. `POST /auth/reset-password` validates token + 6-char minimum + marks token used.
- **AOP Forms multi-doc upload**: new `POST /api/documents/bulk` (max 50 files / 25 MB each). UI Upload dialog now accepts `multiple` files, lists them with remove buttons before sending.
- **Document folders (2-level)**: new collection `document_folders` + endpoints `GET/POST/PUT/DELETE /api/document-folders`. Backend enforces max 2 levels deep (creating a 3rd-level subfolder returns 400). Frontend drill-down — root folders → subfolders → docs. Documents can be uploaded directly into a folder via dropdown.
- **Admin permission fix**: added `documents` tab to `ADMIN_ROLE_TABS['full']` and `['operations_manager']` so full-admins can create/rename/delete folders (was missing — caught by testing agent, fixed before ship).
- **Members directory filter/sort**: status / tier / chapter Selects + Sort dropdown (name / chapter / tier / recently-joined). useMemo'd filtering preserves search query. Clear-filters button surfaces when any non-default filter active.
- **Hours review enrichment**: Admin Hours queue card now displays hours pill (large), member name, AOP-related/Other badge, status badge (pending/approved/rejected colour-coded), date, agency name, "What did they do" box, and "Verification contact" grid showing host name + clickable email + clickable phone.
- **Cascade delete member**: `DELETE /api/members/{id}` now hard-deletes user record, RSVPs, checkins, hours, awards, photos, documents, pending applications, password tokens, omega tributes, chat notifications, and member-created albums. Chat messages are soft-deleted (body replaced with "(message removed — member deleted)", sender_name="Deleted Member") so other group members keep their thread context. PayPal transactions are kept for accounting but anonymized (`user_name="Deleted Member"`, `anonymized=true`). The user is also removed from all conversation `member_ids` lists.
- **MacBook Safari fixes**: confirmed admin notification email fires on every `/auth/apply` submission (`_send_application_admin_notification`). Email inputs across Login/Apply/ForgotPassword have `autoCapitalize=none`, `autoCorrect=off`, `spellCheck=false`, `inputMode=email`. Submit handlers trim+lowercase email and trim password.
- **Testing**: 13/13 backend pytest passing in `/app/backend/tests/test_phase_n.py` after the documents-tab fix; frontend flows verified by testing agent iteration 17 + main-agent self-verification of the doc-folder 2-level enforcement.

### Phase Q — RSVP QR digital tickets + admin scan check-in + chapter logos + Safari fixes (2026-06-02)
- **RSVP confirmation email with QR digital tickets** — `POST /events/{id}/rsvp` now stores a `ticket_id` (uuid) on the member RSVP and a `ticket_id` on each guest. After insert, `send_rsvp_ticket_email` is dispatched as a background task; Resend delivers ONE email to the member that contains a separate QR card per attendee (member + each named guest). QR encodes a signed JWT `{event_id, ticket_id, kind, ticket_type, name}` pointing at `${FRONTEND_URL}/checkin/<jwt>`. Editing guests via `PUT /events/{id}/rsvp/guests` preserves matching ticket_ids (case-insensitive trim on guest name) and re-sends the email with refreshed QRs.
- **Per-person ticket types** — `GuestIn.ticket_type` + `EventRsvpIn.ticket_type` accept `Literal['vip','all_access','general','guest','speaker','volunteer']` (Pydantic rejects anything else with 422). New `MemberTicketPicker` on `/events/:id` lets the member pick VIP / All Access / General before clicking RSVP on a sub-event that allows ticket types. `GuestManager` exposes a per-guest ticket Select inside the manage-guests dialog.
- **Scan-to-check-in flow** — new endpoints `GET /api/checkin/lookup/{token}` (public — returns event + ticket info) and `POST /api/checkin/scan/{token}` (admin-only — creates the check-in idempotently). New page `/checkin/:token` reached when an admin scans the QR with their phone camera. Page auto-runs the scan if admin is logged in, shows the green Checked-in card, then offers "Scan another" or "Open event check-in list". Logged-out visitors see the amber "Admin login required" card with a button that routes to `/login?next=/checkin/<token>` for one-click resume.
- **Chapter logos on public Chapters page** — `Chapters.jsx` now renders `mediaUrl(c.logo_url)` as a 16×16 rounded image when set (with `chapter-logo-{id}` testid), falls back to initials.
- **MacBook Safari fixes**:
  - `POST /auth/apply` now schedules `_send_application_admin_notification` — an admin-notification Resend email to every full-admin + membership-manager containing the applicant's name, email, line, state, intake date and a one-tap "Open Admin → Members" CTA. Previously the application went straight into the DB with no notification, leaving admins unaware.
  - `RESEND_FROM` switched to verified `Alpha Omega Phi <tickets@aop-app.org>` so the email actually leaves Resend (instead of being silently rejected by the `onboarding@resend.dev` sandbox-only sender).
  - `Login.jsx` + `Apply.jsx` email inputs gained `autoCapitalize="none"`, `autoCorrect="off"`, `spellCheck="false"`, `inputMode="email"`. Both form `onSubmit` handlers `.trim()` + `.toLowerCase()` the email and `.trim()` the password before sending. Login also accepts a `?next=` query string and routes there after success.
- **Test coverage**: 11/11 backend pytest pass in `/app/backend/tests/test_phase_m.py`; frontend flows verified by testing agent iteration 16; logged-out checkin flow self-verified by main agent in fresh-cookie Playwright context.

### Phase P — 12-item batch frontend (Photos rebuild, Meetings, Anniversary RSVP+check-in, Admin uploaders, Chat group pic) (2026-06-02)
- **Photos UI rebuild** — `/photos` now renders as an album-grid index (47 seeded "official" albums) → click an album → photo grid with `Upload photos` (multi-file) + `New album`. Multi-file upload posts to `POST /api/photos/bulk` (max 50 files / 100 MB). `POST /api/photos/albums` lets any logged-in member create a named album (case-insensitive uniqueness enforced).
- **Album delete rules** — `DELETE /api/photos/albums/{id}`: default albums 400; creator or any admin succeeds; everyone else 403. Album list response includes `created_by` so the frontend can hide the delete button when the viewer isn't the owner.
- **Anniversary tree visibility** — `GET /api/events` filters `parent_event_id IN [None, '']` by default so members see only the umbrella `Alpha Omega Phi 10-Year Anniversary` parent on the Events list. Clicking into the parent opens the 5 sub-events panel: Transportation to Sip & Paint, Sip & Paint, Sneaker Ball Banquet, Transportation to Top Golf, Top Golf — each with a TICKETS badge.
- **Unlimited guests** — `EventRsvpIn.guests` accepts any number; manual test confirms 20 guests on Top Golf RSVPs cleanly and increments `event.guest_count`. RSVPing the umbrella event is blocked (`400 'umbrella'`).
- **Admin event check-in (sub-events)** — Existing `CheckInDialog` already supports all 6 ticket types (VIP, All Access, General Admission, Guest, Speaker, Volunteer). Verified end-to-end for both member-check-in and named-guest-check-in modes.
- **Admin image uploaders** — `CauseDialog` in Admin → Donations now has an Upload button alongside the URL input, posting to `POST /api/causes/upload-image`. Chapters logo (`/api/chapters/upload-logo`) and News cover (`/api/news/upload-image`) were already wired in previous session — re-verified.
- **Chat group picture (optional)** — `NewChatDialog` now reveals a "Group picture (optional)" uploader when 2+ members are selected. File posts to `POST /api/chat/upload` and the resulting `/api/files/…` URL is attached to `POST /api/conversations` as `avatar_url`. Removal button clears the staged picture before submit.
- **Schedule a Meeting page** — `/schedule-meeting` route is now wired in `App.js` (missing import added). Full CRUD UI (`MeetingCard` + `MeetingEditor`) lets admins publish booking cards with photo, name, title, description, button label, and destination URL. Edit and delete affordances on hover.
- **Gear mobile checkout** — Re-verified 390px viewport: image + Color + Size + Qty + PayPal panel all fit in a single vertical scroll. No clipping.
- **Test coverage**: 27/27 backend pytest pass in `/app/backend/tests/test_phase_l.py`; frontend flows verified by testing agent iteration 15.

### Phase O — Mobile auth via Bearer tokens + Full-admin expiry edit + Gear redesign (2026-06-01)
- **Mobile auth fix (Critical)** — iOS Safari was evicting cookies, causing "Not Authenticated" on profile save + logout on pull-to-refresh. Fix is dual-path: cookies still set for desktop, but tokens are ALSO returned in JSON body by `/auth/login`, `/auth/register`, `/auth/refresh`. Frontend stores them in `localStorage` (`aop_at`, `aop_rt`) and attaches `Authorization: Bearer <token>` on every request via axios request-interceptor. `/auth/refresh` accepts token via body `{refresh_token}` OR Authorization header OR cookie. `get_current_user` already accepted Bearer. End-to-end verified by testing agent: with ALL cookies cleared on 390px viewport, profile save still works.
- **Full-admin can edit `membership_expires_at`** — `EditMemberDialog` now renders the field as a real date `Input` (gated to `isFullAdmin`). Backend `admin_update_member` enforces "Only full Admins may change roles, tiers, or the membership expiration date." Explicit expiry overrides the auto-recompute from `join_date`.
- **Gear redesign (admins)** —
  - Editable page banner via `GET/PUT /api/gear-page` (app_settings doc): hero_image + title + subtitle + intro paragraph.
  - `GearEditor` dialog: name, price, category, SKU, description, cover photo (URL + upload via `/api/gear/upload`), **size toggles for standard S/M/L/XL/XXL/3XL + custom-size input**, **color list with one photo per color (`color_images: [{color, image_url}]`)**, in-stock toggle.
  - `GearItemIn` + `GearItemUpdateIn` + `gear_out` carry `color_images`.
- **Gear redesign (members)** —
  - Item dialog shows color buttons + size buttons + qty + total. Selecting a color SWAPS the displayed image to the per-color photo (falls back to cover_image if not tagged).
  - PayPal create-order accepts `gear_color` + `gear_size` (added to `PayPalOrderIn`), persists on the transaction, and the description renders `"AOP Gear: Item Name (red · M)"` for fulfillment clarity.
  - Checkout disabled until both required variant selections are made; clear inline warning.
- **Test coverage**: 22/22 pytest in `/app/backend/tests/test_phase_k.py`; full Playwright frontend flow including mobile-auth localStorage path verified by testing agent iteration 14.

### Phase N — Mobile-first auth + Profile social + chapter freedom + Founder tier + Omega banner + AOP Forms preview (2026-06-01)
- **Auth refresh** — Fixed "logs out on refresh" (mobile Safari ITP evicts access cookie). `AuthContext` now retries `/auth/me` via `/auth/refresh` before flipping to logged-out. `lib/api.js` axios response-interceptor transparently refreshes on any 401 and replays the original request once (de-duplicated).
- **Admin Console mobile** — TabsList (13 admin tabs + 5 Email sub-tabs) is now a horizontal `inline-flex w-max` strip inside `overflow-x-auto scrollbar-hide` on small screens; verified scrollWidth=1242 vs clientWidth=342 at 390px viewport.
- **Renew button removed** — `/profile` no longer shows "Renew for 1 year". `POST /api/members/me/renew` now returns 410 Gone — members must pay annual dues via PayPal to extend.
- **Founder tier** — new tier order=7, lifetime, $0 dues. Reconciled at startup. Total tier count: 7.
- **Social media profile fields** — added `facebook_url`, `instagram_url`, `linkedin_url`, `twitter_url`, `tiktok_url`, `pinterest_url`, `youtube_url`, `website_url` to `ProfileUpdateIn`, `public_user`, and the `/profile` form. Members manage on Profile → "Social profiles" section.
- **Member directory cards** — full rebuild. Rectangular 4:3 photo at top, name, email, phone, full address (street/city/state/zip/country), chapter, status pills, social-media icons that launch the URL in a new tab. Detail dialog same layout.
- **Intake date approval workflow** — When a member changes `intake_completed_at`, value goes to `pending_intake_completed_at` (not the live field) and admin sees it in a yellow "Pending intake date changes" panel on Admin → Members. Endpoints: `GET /admin/pending-intake-changes`, `POST /admin/members/{id}/intake-completion-review {action: approve|reject, note}`. Review actions logged to `intake_review_log[]`.
- **Chapter freedom** — `ChapterDialog` now uses a free-text `<Input>` (not `Select`). Backend `POST /chapters` allows any name but enforces case-insensitive uniqueness (`re.escape` regex) so duplicates 400 with a clear message. Admin can create Carolinas, Midwest, Northeast, PacificNW, etc.
- **Profile Chapter dropdown** — no longer filtered to 4 official; members pick from ALL chapters.
- **Trendsetters logo** — Home + Navbar now use `https://customer-assets.emergentagent.com/job_club-express-lite/artifacts/k67x4iui_Trendsetters%20logo.png` instead of "A" tile / older AOP logo.
- **Omega memorial banner** — `HeroEditor` removed (admins use the tribute system instead). `BiographyBody` rebuilt as a large memorial banner: rectangular portrait (h-72→h-96, w-56→w-80), centered name/dates, optional epitaph block-quote, long-form bio. Layout matches clubexpress aop.clubexpress.com reference. Grid changed from `sm:grid-cols-2 lg:grid-cols-3` to vertical `space-y-10` stack so each tribute is full-width.
- **AOP Forms picture upload** — bigger preview pane (h-64 instead of h-48) with a "Preview" header bar, `onError` opacity dimming, and `mediaUrl()` wrapping the `<img>` src so the preview renders regardless of REACT_APP_BACKEND_URL origin.
- **`mediaUrl()` helper in lib/api.js** — turns relative `/api/files/...` paths into absolute backend URLs; used by AvatarUploader, Navbar avatar, Directory, Omega CoverOrAvatar, Documents (form-link card + preview), and Omega tribute photo preview.
- **Test coverage**: 21/21 pytest in `/app/backend/tests/test_phase_j.py`; 17/17 frontend flows verified by testing agent iteration 13.

### Phase M — Omega hero photo, AOP Forms quick links, Life Member Candidate tier, Welcome email transparency (2026-02-28)
- **Omega Chapter featured photo** (mirrors clubexpress page): new `GET /api/omega/hero` (public) + `PUT /api/omega/hero` (admin) backed by `app_settings` collection with key `omega_hero`. Banner image + optional title + caption render at top of `/omega` between the header and the tributes grid. Admin manages it via "Edit featured photo" dialog with URL input + drag-and-drop upload (reuses `/api/omega/upload`).
- **AOP Forms "Quick links" picture cards**: new `form_links` collection + `GET /api/form-links` (public), `POST/PUT/DELETE /api/form-links/{id}` (admin), `POST /api/form-links/upload` (admin, 10MB cap). Renders as a 3-up grid above the documents table on `/documents`. Each card has cover image, title, description, external-link icon; clicking opens the URL in a new tab. Admin sees Add link / Edit / Delete; members see only cards.
- **New tier — Life Member Candidate** (order=4, annual_dues=$100, is_lifetime=False). Reconciled at startup. Silver Life Member moved to order 5, Gold Life Member to order 6.
- **Welcome email on application approval**: `_send_approval_email` reworked to return `(ok, detail)`. Subject changed from "your application was approved" → **"Welcome to Alpha Omega Phi"**. Body intro now welcomes member by name and lists what the portal offers. `POST /admin/applications/{id}/review` response now includes `welcome_email_sent` + `welcome_email_detail`. Admin UI surfaces a `toast.warning` (8s) with the exact Resend rejection reason when delivery fails — no more silent failures.
  - **Known Resend constraint**: `RESEND_FROM=onboarding@resend.dev` (sandbox) only delivers to the API key owner's email. To send Welcome emails to every applicant, verify a domain at resend.com/domains and update `RESEND_FROM` in `/app/backend/.env`.
- **Test coverage**: 19/19 pytest pass in `/app/backend/tests/test_phase_i.py`; frontend flows verified by testing agent iteration 12.

### Phase L — Omega tab tribute templates + backgrounds (2026-02-28)
- **Templates (admin-selectable, exactly 3 per user choice a/b/c)**: `biography`, `memorial-card`, `in-service`. Legacy `classic` / `portrait` removed (Pydantic Literal now rejects them with 422). `in-service` template renders a military brief layout: rank header → photo + Branch/Service/Home/Interred dt-dd grid → epitaph blockquote + synopsis.
- **Backgrounds (admin-selectable, exactly 7 per user choice #1)**: `american-flag` (white-overlay flag stripes + star canvas), `navy-starfield` (radial stars on navy gradient), `marble`, `sepia` (parchment), `solid-red`, `solid-navy`, `solid-white`. Legacy `navy-radial`/`ivory-soft`/`patriot-stripe`/`midnight`/`parchment` removed.
- **New tribute fields**: `rank` and `service_dates` (free-text) added to `OmegaTributeIn` / `OmegaTributeUpdateIn` / `tribute_out` / auto-card builder. Surfaced as inputs in the Admin TributeBuilder dialog and rendered inside the In-Service body.
- **Admin UX**: `TributeBuilder` dialog on `/omega` (admin-only) provides member search-picker, template + background dropdowns, photo URL + upload, rank, service_dates, born / entered-omega dates, resting place, epitaph, synopsis, biography, and a **live preview pane**. Edit / Delete buttons appear on each card.
- **Member UX**: `/omega` grid renders the chosen template + background. Non-admins see no add/edit/delete controls.
- **Test coverage**: 14/14 pytest pass in `/app/backend/tests/test_omega_tributes.py`; frontend flows verified by testing agent iteration 11.

### Phase K — Lifetime members + tier-change gating (2026-02-28)
- **Tier model**: `is_lifetime: bool` added to AOP_TIERS. Silver Life Member + Gold Life Member flagged `is_lifetime=true`, `annual_dues=$0`. Exposed in `/api/tiers` response.
- **User model**: `is_lifetime_member: bool` persisted on user doc. Synced automatically whenever a tier is assigned (via `/members/{id}/tier`, full PUT `/members/{id}`, or admin_create_member). Backfilled at startup via `reconcile_tiers` for any existing members on lifetime tiers.
- **No expiration for lifetime members**: `public_user` returns `membership_expires_at=None` and `status="active"` (never "expired"/"grace") for lifetime members regardless of stored value. Switching back to a non-lifetime tier re-establishes a 1-year expiration from now (or +extend_days if specified).
- **Tier changes locked to full Admin**: `PUT /members/{id}/tier` → 403 "Only full Admins may change member tiers" for Operations/Membership/Governor Managers. Full PUT `/members/{id}` with `tier_id` change also blocked (same 403 message covers role + tier).
- **Frontend UI gating**: Admin → Members inline tier dropdown is `disabled` for non-full-admins; EditMember dialog tier select disabled with "(only full Admins can change)" hint.
- **UI hides expiration for lifetime members**:
  - **Member Card**: shows `Lifetime · no renewal` instead of "Membership expires" row.
  - **Profile**: membership banner shows `Lifetime member · No renewal required — your membership never expires.` PayPal dues UI + Renew button hidden.
  - **Admin Members table**: "Expires" column shows red "Lifetime" badge for life members; the inline +1yr button is also hidden.

### Phase J — Chat SMS notifications + 15-min digest + opt-out (2026-02-28)
- **Chat digest bumped to 15 minutes** (was 5; user range request 10–20).
- **Twilio SMS integration**, graceful no-op when `TWILIO_ACCOUNT_SID` / `TWILIO_AUTH_TOKEN` / `TWILIO_FROM_NUMBER` are absent. SDK pinned at `twilio==9.10.9`. `_normalize_phone_e164` handles US `10-` or `11-`digit inputs and any `+`-prefixed E.164.
- **Chat digest loop now sends both email and SMS** per the recipient's opt-in flags. SMS body (per user choice 2a): `"You have a new message in Alpha Omega Phi chat. Open the portal to read it: {FRONTEND_URL}/chat"`.
- **Per-user opt-out**: new fields `chat_email_notifications` (default true) and `chat_sms_notifications` (default true) on user model, exposed in `public_user`, settable via `PUT /api/members/me`. `queue_chat_notifications` skips fully opted-out recipients at queue time; the digest worker also respects them.
- **Profile UI**: new **Notifications** tab with two `Switch` rows (Email me / Text me). SMS row is disabled with explanatory copy if the user has no phone on file. Save button persists prefs.
- **Verified via curl**: opted-out → no row queued; opted-in → row queued with `due_at = created_at + 15 min`. Twilio cleanly disabled in current preview env.

### Phase I — Apply-with-password, Mgr scoping, member transactions, Personnel Brief PDF (2026-02-28)
- **Applicant chooses password during /apply**: `PublicApplicationIn` gains a required `password` field; `Apply.jsx` adds Choose / Confirm password inputs. Approval no longer issues a token — the user logs in with the password they chose. Approval email simply says "you can sign in now."
- **Set-password page removed**: `/set-password` route now redirects to `/login`. `_send_set_password_email` and the token table remain in place for legacy back-compat (harmless if unused).
- **Operations Manager + Membership Manager chapter scoping**: `is_chapter_scoped` + `chapter_scope_user_ids` now scope these roles when they have a `chapter_id` assigned. Verified: Membership Manager assigned to Texas sees 4 members in `/reports/members` vs full admin's 22. Same scoping applies to `/admin/stats`, `/api/hours`, `/api/reports/*`, `/api/causes/{id}/donations`, `/api/transactions`.
- **Member-facing transactions page**: new `/transactions` route + `Transactions.jsx` with type/status filters, summary cards (total / dues / donations / gear), full table, CSV export. Linked from the existing Profile → Transactions tab.
- **Personnel Brief PDF**: new `GET /api/reports/personnel-brief/{user_id}/pdf` endpoint generates a branded multi-section PDF (identity, service summary stats, awards/ribbons, volunteer hours table, events attended, transactions table) using ReportLab. Frontend Reports → Personnel Brief dialog now has Download PDF button next to Print.
- **Welcome email** continues to work on `POST /api/admin/members`. Approval email (`_send_approval_email`) added for the apply flow.

### Phase H — Public registration, anniversary 2027, role-gating, attendance, intake fields, welcome email (2026-02-28)
- **Public registration with admin approval**: new `/apply` page collects first/last name, email, line name, intake line, intake completion date (month/year), full mailing address (state/zip/country). Admin reviews in Admin → Members → "Pending applications" panel. Approval creates the user with an unusable password + a 7-day single-use `password_set_tokens` row + sends a Resend email to `/set-password?token=…` to finish activation. Replay-protected (used flag + expires_at). Rejection sends a courtesy email with an optional reason.
- **Welcome email**: `send_welcome_email` is called best-effort on `POST /api/admin/members` — sends the user their email + temporary password with a "change on first login" CTA.
- **Anniversary reconciliation to 29-31 July 2027**: `seed_anniversary_subevents` now overwrites parent start/end and sub-event dates on every startup. Day mapping: Sip & Paint + Transportation Sip&Paint (29 Jul), Banquet (30 Jul), Top Golf + Transportation Top Golf (31 Jul). Stale anniversary-tagged events outside the canonical list are deleted along with their RSVPs/checkins.
- **Role-change gating**: `update_member_role` and `admin_update_member` both `403` when `admin_role_of(admin) != "full"`. Operations Manager and Membership Manager can edit members but cannot promote/demote roles.
- **Member Card additions**: avatar image (with fallback), state/zip in address row, country row, intake line, intake completed, date joined (from `join_date`).
- **Reports — Members enriched**: each row now includes `events_attended_count`, `events_attended` (array with event_title + ticket_type + checked_in_at) and `guests_registered_count`, `guests_registered`. Table columns + CSV export updated.
- **Reports — new RSVPs tab**: `GET /api/reports/rsvps` returns every RSVP across selected event or parent_event; rows include member, RSVP'd timestamp, ticket_type (from admin check-in), check-in timestamp, and full guest list. Frontend tab + CSV export.
- **Member self-check-in**: `POST /api/events/{id}/self-check-in` (member auth) — appears on EventDetail sidebar after `start_at` has passed; idempotent.
- **Intake fields editable**: Profile + Admin → Members → Edit dialog both have `intake_line` text input + `intake_completed_at` Month/Year input. Public `/apply` form already collects them and they flow through approval.
- **Gear mobile scroll fix**: Gear dialog wraps content in a `max-h-[92vh]` grid with `overflow-y-auto` on the details column so PayPal area is scrollable on phones.
- **Test coverage**: 24/24 pytest pass in `/app/backend/tests/test_phase_h.py`; testing agent iteration 10 covered all frontend flows; the single gap (EditMemberDialog missing intake inputs) was fixed and re-verified manually.

### Phase G — Avatar, Profile expansion, Join-date renewal, Email individual, Chat email digest, Event guests, 10-Year Anniversary (2026-02-28)
- **Profile expansion**: `state`, `zip_code`, `country` added to user model + `public_user` payload + `ProfileUpdateIn` + admin create/update member; surfaced in `/profile` form (3-column row under Address) and Admin → Members → Edit dialog.
- **Admin edits Date Joined**: `AdminUpdateMemberIn.join_date: datetime`. When set, backend recomputes `membership_expires_at = join_date + 365d` unless admin also overrides expires. Edit dialog shows a live "Membership expires (auto from join date)" preview.
- **Avatar upload** (`/api/members/me/avatar`, multipart, 10 MB cap, jpg/png/gif/webp). Stored in object storage under `avatars/{user_id}/{file_id}/{filename}`, registered in `chat_files` so `/api/files/{path}` resolves it. New `<AvatarUploader />` component on Profile with two buttons: **Upload** (file picker; phone gallery + laptop) and **Take photo** (in-browser dialog using `navigator.mediaDevices.getUserMedia` + canvas capture; flip-camera button; graceful error if permission denied).
- **Email blast: Individual member segment**. Compose tab adds segment option `Individual member` with member-search picker; submission maps to backend `segment="custom"` + `custom_user_ids=[picked_id]`. Preview returns `recipient_count=1`.
- **Chat → email digest** (5-min debounce). On each `POST /conversations/{id}/messages`, backend inserts one `chat_notifications` doc per recipient (sender excluded) with `due_at = now + 5 min`, `status="pending"`. `POST /conversations/{id}/read` flips matching pending rows to `cancelled`. Background `_chat_digest_loop` runs every 60s, batches by `(recipient_id, conversation_id)`, sends one consolidated Resend email with up to 10 message previews, marks rows `sent`/`failed`. Honors `RESEND_FROM`.
- **Events: guest registration & count**. `RSVP` endpoint accepts body `{guests: [{name, email?, phone?}]}`; `event.guest_count` incremented on RSVP / decremented on cancel. New `PUT /api/events/{id}/rsvp/guests` updates the list without toggling. Event sidebar shows "+N guests" and the **GuestManager** dialog lets members add/remove guests post-RSVP.
- **10-Year Anniversary umbrella + 5 sub-events** (idempotent seed at startup via `seed_anniversary_subevents`):
  - Parent: `Alpha Omega Phi 10-Year Anniversary` (category=anniversary).
  - Sub-events: `Transportation Buses to Sip and Paint`, `Sip and Paint`, `Transportation Buses to Top Golf`, `Top Golf`, `Banquet`.
  - `allows_ticket_types=True` on Sip & Paint, Top Golf, Banquet only. Anniversary date controlled by `ANNIVERSARY_AT` env var (default `2026-10-18T17:00:00Z`).
  - New `GET /api/events/{parent_id}/sub-events` endpoint and `SubEventsPanel` UI on parent's detail page.
  - Admin check-in `ticket_type` literal expanded to include `all_access` (alongside `vip` / `general`). The CheckInDialog filters available types by `event.allows_ticket_types`.
- **Test coverage**: 18/18 pytest pass in `/app/backend/tests/test_phase_g.py`; full frontend flows verified by testing agent iteration 9.

### Phase F — Admin sub-roles, Governor chapter scoping, Member Card ribbons, Hours validation (2026-02-28)
- **Sub-role admin tabs**: `ADMIN_ROLE_TABS` map at `server.py:227-232` defines allowed Admin-console tabs for each `admin_role`: `full` (all 13), `membership_manager` (dashboard/members/chapters/tiers/events/awards/reports/email), `operations_manager` (dashboard/members/chapters/events/hours/causes/reports/news), `governor_manager` (dashboard/hours/causes/reports — and chapter-scoped).
- **`/api/admin/permissions`** returns `{admin_role, tabs, chapter_scoped, scoped_chapter_id}`. Admin.jsx gates `<TabsTrigger>` / `<TabsContent>` rendering off this.
- **Server-side defense-in-depth**: `admin_tab_dep(<tab>)` dependency factory applied across all restricted-tab endpoints (email/news/pages/chapters/tiers/events+check-ins/awards+grants/gear/members admin CRUD/role/chapter/tier/status/causes/reports/personnel-brief/hours-review). Governor/Membership/Operations managers get `403 "Your admin role does not have access to <tab>"` on direct API calls — no longer just client-side gating.
- **Governor chapter scoping**: `chapter_scope_user_ids(admin)` + `is_chapter_scoped(admin)` helpers. Endpoints `/api/admin/stats`, `/api/hours`, `/api/reports/{members,hours,donations}`, `/api/causes/{id}/donations`, `/api/transactions` apply `{chapter_id: scoped_cid}` or `{user_id: {$in: chapter_user_ids}}` filter when the caller is a `governor_manager`. Full admin sees everything.
- **Member Card UI**: `MemberCardDialog` in `Admin.jsx` now fetches `/api/members/{id}/awards` and renders all earned Ribbons as red pill badges with grant date tooltips. Surfaces email/phone/address/birthdate/branch/chapter/member type/joined/expires/bio. Bottom disclaimer: "Secure data (passwords, payment methods, transactions) is intentionally hidden."
- **Hours form**: `LogHoursDialog` wrapped in `<form onSubmit>` with `required` on all 7 user-input fields (hours, date, agency, activity, host name/email/phone). Empty submit blocked by native browser validation.
- **Test coverage**: 65/65 parametrized tests at `/app/backend/tests/test_phase_f_followup.py` + 23/24 at `/app/backend/tests/test_phase_f.py` (the 1 prior gap is now closed).

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

### Iteration 29 — Profile extras + admin hours-adjust + member self-download brief + MacBook founders bug fix (2026-06-04)
- **Personnel Brief PDF redesigned** (`_personnel_brief_pdf_response`): header with photo + title + name + line name + email + phone, then 10 numbered navy-banner sections — §1 Personal Info, §2 Org Info, §3 Civilian Education (chronological), §4 Languages (most-recent year first), §5 Financial Obligations / Annual Dues (last 5), §6 Donations (last 5 — cause/amount/date), §7 Community Service (current-year only — agency / event_type / hours / status / date), §8 Awards (with 1st/2nd/3rd ordinal per award), §9 Events (current-year check-ins only), §10 Assignment History (current first).
- **Annual Tax Donation Letter** (`/api/me/tax-letter/pdf?year=...`): member-only PDF that sums all COMPLETED dues + donations + fees inside a calendar year. Includes EIN 82-0794957, signature line block (Cory T. Burnett / Co-Founder / Alpha Omega Phi Military Fraternity & Sorority, Inc.) with Cory's hand-signed image (`/app/backend/assets/cory_signature.png`) embedded directly above the block. Defaults to last completed year. Pending tx are excluded.
- **Assignment History admin UI** (`AssignmentHistoryEditor.jsx`): single-line rows with Start / End-or-Current / Chapter / State / Location / Duty Title / Rank. 8-rank dropdown (Grand Sirius 5★ → Master/Senior/Advanced/Junior Sirius → Eagle/Clover/Guardian). Current toggle disables End-date input. ↑/↓ reorder and Remove available per row. `RANK_CHOICES` Literal + `AssignmentEntry` model + `AdminUpdateMemberIn.assignment_history`.
- **Profile additions**: "Tax letter" button with year picker (current + 5 prior) next to "Download my brief".
- **Tests**: 12/12 new pytest + 85/85 full regression in ~33 s.


- **MacBook founders fix**: `mediaUrl()` (in `lib/api.js`) now rewrites stale `*.emergentagent.com` preview-origin URLs to current `REACT_APP_BACKEND_URL`. All `<img>` on Home.jsx wrap src with `mediaUrl()`. Fixes the production aop-app.org Safari issue where founder images saved with preview hostnames couldn't load.
- **Admin can adjust hours value at any time**: `HoursReviewIn` accepts `status='pending'` (revert path) + optional `hours / activity / agency_name / event_type`. Audit fields `hours_adjusted_by_name` + `hours_adjusted_at` stamped on adjustment. `AdminHoursActions` in Hours.jsx adds an inline number-input "✏️ Edit hrs" on every row — pending OR approved.
- **Profile extras** (member self-service): `marital_status` dropdown beside Phone, up to 3 spoken languages (speaking/reading/writing proficiency + year), up to 5 civilian degrees (level + type + field + institution + grad month/year). New `ProfileExtrasEditor.jsx`.
- **Member can download own Personnel Brief**: `GET /me/personnel-brief` + `GET /me/personnel-brief/pdf`. `DownloadMyBriefButton` in Profile header.
- **Tests**: 13/13 new + 73/73 full regression.

### Iteration 30 — New Personnel Brief 10-section layout + Annual Tax Letter PDF + Assignment History admin (2026-06-04)
- **Personnel Brief PDF redesigned** (`_personnel_brief_pdf_response`): header (photo + title + name + line + email + phone), then 10 numbered navy-banner sections covering Personal Info / Org Info / Civilian Education (chronological) / Languages (most-recent year first) / Financial Obligations (last 5 dues) / Donations (last 5) / Community Service (current year only) / Awards (with 1st-2nd-3rd ordinal) / Events (current-year check-ins only) / Assignment History (current first).
- **Annual Tax Donation Letter** (`GET /api/me/tax-letter/pdf?year=...`): member-only PDF summing all COMPLETED dues + donations + fees inside a calendar year. Includes EIN 82-0794957, hand-signed Cory T. Burnett signature image above his Co-Founder block. Defaults to last completed year. Pending tx excluded.
- **Assignment History admin UI** (`AssignmentHistoryEditor.jsx`): single-line rows with Start / End-or-Current / Chapter / State / Location / Duty Title / Rank. 8-rank dropdown (Grand Sirius 5★ → Master/Senior/Advanced/Junior Sirius → Eagle/Clover/Guardian). Current toggle disables End-date. ↑/↓ reorder + Remove per row.
- **Profile additions**: "Tax letter" button with year picker (current + 5 prior) next to "Download my brief".
- **Tests**: 12/12 new pytest + 85/85 full regression in ~33 s.


### Iteration 25 — Zeffy receipt validation + auth/payments route extraction (2026-06-03)
- **Backend `routes/payments.py`** (new) — extracted Zeffy + transaction routes from `server.py`:
  - `classify_zeffy_receipt()` — regex-based format detection. Returns `'rct'` (RCT-XXXX-XXXX), `'zf'` (ZF-XXXXXX), `'email'` (donor@example.com), `'alnum'` (10-40 char alphanumeric id), or `None`.
  - `GET /api/payments/zeffy/validate?value=…` — live format-validation endpoint. Returns `{valid, format, label, trusted, will_auto_approve}`.
  - `POST /api/payments/zeffy/confirm` now persists `zeffy_receipt_format` on the transaction doc.
  - Moved: `GET /api/payments/zeffy/config`, `PUT /api/transactions/{id}/approve-zeffy`, `GET /api/transactions`, `DELETE /api/transactions/{id}`, `GET /api/me/transactions`, `POST /api/transactions`.
- **Backend `routes/auth.py`** (new) — extracted 5 core auth routes:
  - `POST /api/auth/register`, `POST /api/auth/login` (email OR username), `POST /api/auth/logout`, `GET /api/auth/me`, `POST /api/auth/refresh` (cookie + JSON body + Bearer header).
  - Brute-force lockout (5 attempts / 15 min) preserved.
- **Frontend `ZeffyCheckout.jsx`**: live debounced format validation (300ms) with green-checkmark hint showing detected format + "eligible for instant approval" callout when the member is trusted. New `data-testid="zeffy-format-hint"`.
- **Frontend `Reports.jsx`** (admin dues queue): new format badge on each approval row — sky-blue ✓ for recognised formats (RCT-####, ZF-#, email, alnum id), rose ⚠ "unrecognised" for free-text. Helps admins spot fakes at a glance. `data-testid="zeffy-format-badge-{txId}"`.
- **Refactor progress**: `server.py` 7,053 → 6,711 lines (−342 lines, −5%). Modules under `routes/` now: pages, site_settings, ai, news, chapters, tiers, payments, auth.
- **Tests**: 28/28 backend pytest pass in `/app/backend/tests/test_iteration25_auth_zeffy.py`. Frontend live-validation + submit flow verified.

### Iteration 28 — Paid events + AOP events-inbox CC + Optional ticket types + Set-password email blast (2026-06-04)
- **MacBook founders fix**: `mediaUrl()` (in `lib/api.js`) now rewrites stale `*.emergentagent.com` preview-origin URLs to the current `REACT_APP_BACKEND_URL`. All `<img>` tags on Home.jsx (founders, leadership, avatars, event covers, news covers) now wrap their src with `mediaUrl()`. Root cause: founder images were uploaded while editing in preview and saved with the preview hostname; production page (aop-app.org) couldn't load them due to Safari ITP / origin restrictions.
- **Admin can adjust hours value at any time**: `HoursReviewIn` accepts `status='pending'` (revert path) + optional `hours / activity / agency_name / event_type`. Audit fields `hours_adjusted_by`, `hours_adjusted_by_name`, `hours_adjusted_at` stamped on adjustment. Front-end `AdminHoursActions` (Hours.jsx) adds an inline number-input "✏️ Edit hrs" on every row regardless of status — pending and approved alike. Adjustment count audit visible inline.
- **Profile extras** (member self-service): added `marital_status` (single dropdown placed beside Phone), up to 3 spoken languages (`{language, speaking, reading, writing, year_accomplished}`), up to 5 civilian degrees (`{degree_level, degree_type, field_of_study, institution, graduation_month, graduation_year}`). New `ProfileExtrasEditor.jsx` (`MaritalStatusField`, `LanguagesEditor`, `CivilianDegreesEditor`) keeps Profile.jsx tidy. Pydantic models `LanguageEntry` + `CivilianDegreeEntry` validate sub-fields. `public_user` surfaces them.
- **Member can download own Personnel Brief**: new endpoints `GET /me/personnel-brief` and `GET /me/personnel-brief/pdf` (uses `_personnel_brief_data` helper shared with admin endpoint). `DownloadMyBriefButton` lives in the Profile header.
- **Tests**: 13/13 new pytest cases + 73/73 full regression in ~30s.


- **Paid events**: `Event` model adds `is_paid`, `payment_url` (Zeffy URL), `payment_amount`. Free RSVP on a paid event returns **402**. New `POST /events/{id}/payment/confirm` (Zeffy receipt → pending `event_ticket` tx) + `PUT /transactions/{id}/approve-event-ticket` (admin approval creates RSVP + emails ticket). Mirrors dues flow: trust_zeffy + valid receipt format → auto-approval. Duplicate-payment guard returns 400. `PaidEventCheckout.jsx` is the member-side UI.
- **Events inbox CC**: `send_rsvp_ticket_email` now CC's `EVENTS_INBOX_EMAIL` (default `info@alphaomegaphi.org`) on every RSVP ticket email, including the QR code. Env-configurable.
- **Optional / selectable ticket types**: Event model adds `enabled_ticket_types: List[str]`. Empty = no ticket types. Otherwise admin picks any subset of vip/all_access/general/guest/speaker/volunteer. EventDialog renders 6 checkboxes; both MemberTicketPicker and PaidEventCheckout filter to only enabled types.
- **Bulk-import set-password emails**: `admin_bulk_import_members` now accepts `send_set_password_emails` form field (default true). Each created member gets a 7-day one-time `password_set_token` and a set-password email via Resend. Tokens persist even if email send fails.
- **Reports → Event tickets tab**: new admin queue `EventTicketApprovals` parallel to dues queue. Dues queue filter tightened to `purpose === 'dues'`.
- **Tests**: 15/15 new tests + 60/60 full regression (iter25+27+28) in ~30 s.

### Iteration 27 — Event cancellation + Bulk CSV import + Member Title (2026-06-03)
- **Paid events**: `Event` model adds `is_paid`, `payment_url` (Zeffy URL), `payment_amount`. Free RSVP on a paid event returns **402** "This event requires payment". New `POST /events/{id}/payment/confirm` (member submits Zeffy receipt → pending `event_ticket` transaction). New `PUT /transactions/{id}/approve-event-ticket` (admin approval → creates RSVP + emails ticket). Mirrors the dues flow: trust_zeffy + valid Zeffy receipt format → auto-approval. Idempotent on repeat approval. Duplicate-payment guard returns 400 "already submitted". `PaidEventCheckout.jsx` is the member-side UI (open Zeffy → "I completed payment" → receipt input with live format hint).
- **Events inbox CC**: `send_rsvp_ticket_email` now CC's `EVENTS_INBOX_EMAIL` (default `info@alphaomegaphi.org`) on every RSVP ticket email, including the QR code. Env-configurable.
- **Optional / selectable ticket types**: Event model adds `enabled_ticket_types: List[str]`. Empty list = no ticket types (member RSVPs without choosing). Otherwise the admin picks any subset of `vip/all_access/general/guest/speaker/volunteer`. Admin EventDialog renders the 6 checkboxes; `MemberTicketPicker` and `PaidEventCheckout` filter to only enabled types.
- **Bulk-import set-password emails**: `admin_bulk_import_members` accepts `send_set_password_emails` form field (default true). For each created member, generates a one-time `password_set_token` (7-day expiry) in `db.password_set_tokens` and emails the set-password link via Resend. Result returns `emails_sent_count`. Tokens are created even if Resend fails — admins can re-trigger sends later.
- **Reports → Event tickets tab**: new admin queue (`EventTicketApprovals`) parallel to the dues queue. Approve / Reject buttons with `data-testid="event-ticket-approve-{tx_id}"` and `-reject-{tx_id}`. Dues queue filter tightened to `purpose === 'dues'` so event_ticket txs don't leak in.
- **Tests**: 15/15 new tests in `/app/backend/tests/test_iteration28_paid_events.py`; full regression 60/60 (iter25 + iter27 + iter28) in ~30 s.


- **Event cancellation**: admin can flip an event to "cancelled" via the EventDialog (`data-testid="event-cancelled-toggle"`) with optional reason. Backend stamps `cancelled_at` on flip-on, blocks new RSVPs (400 "This event has been cancelled — RSVPs are closed.") and guest-list edits (400 "guest list is locked"). Event still appears on the calendar/events grid with a red "Cancelled" pill + strikethrough title. EventDetail page shows a prominent banner + reason. Un-cancelling clears `cancelled_at` and re-enables RSVPs.
- **Bulk CSV member import** (`POST /api/admin/members/bulk-import`): admin uploads a CSV (typically a ClubExpress roster export). One user per row; `membership_expires_at = renewal_date + 365 days`. Accepts flexible column aliases (FirstName/First Name/First, Renewal Date/Renewal/Expires, etc.), 9-format title normalization, multi-format date parsing via `dateutil`. Dry-run preview mode returns counts without inserting. Duplicates by email are skipped, not overwritten. Per-row error capture so admins can fix and re-upload. 5 MB cap. Template download at `GET /api/admin/members/bulk-import/template`. New `BulkImportMembersDialog.jsx` component on Admin → Members tab next to "New member".
- **Title field** (optional): Mr. / Mrs. / Ms. / Miss / Dr. / Prof. / Rev. / Hon. / Mx. — added to user model (`u.title`), Profile (member self-edit), Admin New/Edit member dialogs, and Directory display (prefixed before the name).
- **Tests**: 17/17 backend pytest pass in `/app/backend/tests/test_iteration27_features.py`. Bulk import dialog + profile title persistence + event-edit testid all verified.


### P0 — Production polish
- Resend domain verification + update `RESEND_FROM` env to verified address.
- Register Resend webhook URL in dashboard.
- Add Resend webhook signature verification (svix).

### P1 — Refactor & polish (Phase 4 in progress)
- ~~Auth core routes (register/login/logout/me/refresh)~~ ✅ extracted to `routes/auth.py` (2026-06-03).
- ~~Zeffy + transactions routes~~ ✅ extracted to `routes/payments.py` (2026-06-03).
- **Remaining**: `routes/members.py` (~600 lines around `/members/*` admin CRUD), `routes/events.py` (~600 lines), `routes/auth_email_flows.py` (apply/set-password/forgot/reset/change — ~400 lines bundled with email senders).
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
