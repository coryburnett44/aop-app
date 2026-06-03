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

### Phase W — Email-or-username login + URL validation + Founders CMS + cover-photo upload UX everywhere (2026-06-03)
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
