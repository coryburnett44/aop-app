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
### Iteration 128 — Modularization: extract omega / cms_cards / uploads out of server.py (2026-02-27) [REFACTOR]
Long-deferred P1 refactor to keep `server.py` maintainable. Three legacy blocks (Omega Chapter in-memoriam tributes, AOP Form Links + Meeting Cards CMS, generic admin image-upload endpoints) extracted into dedicated modules.

- **`routes/omega.py` (new, ~270 lines)** — full extraction of the in-memoriam surface:
  - `GET /omega` (public deceased+tribute merge), `GET /omega/options`, `POST/PUT/DELETE /omega/tributes/*`, `POST /omega/upload`, `GET/PUT /omega/hero`.
  - Pydantic models `OmegaTributeIn`, `OmegaTributeUpdateIn`, `OmegaHeroIn` and `tribute_out` helper moved along with the routes.
- **`routes/cms_cards.py` (new, ~230 lines)** — AOP Form-Links picture cards + Schedule-a-Meeting cards:
  - `GET/POST /form-links`, `PUT/DELETE /form-links/{id}`, `POST /form-links/upload`.
  - `GET/POST /meeting-cards`, `PUT/DELETE /meeting-cards/{id}`, `POST /meeting-cards/upload-image`.
- **`routes/uploads.py` (new, ~75 lines)** — generic admin image upload helper + wrappers:
  - Internal `_upload_image(file, prefix, user, max_mb)` shared helper (also re-exposed via `register.upload_image` for future re-use).
  - Wrappers: `/chapters/upload-logo`, `/causes/upload-image`, `/news/upload-image`, `/leadership/upload-image`, `/founders/upload-image`, `/events/upload-cover`, `/chat/group-photo-upload`.
- **`server.py` shrinks 4109 → ~3579 lines (−530, ~13%)**. Registration follows the same `register(api, *, db, ...)` pattern used by the other extracted modules.
- **Tests**: `tests/test_iteration128_modularization.py` — 9/9 pass. Verifies module importability, `server.py` no longer owns extracted symbols (`_upload_image`, `tribute_out`, `_form_link_out`, `_meeting_out`), the public endpoints still respond, and full CRUD round-trips on `/form-links` + `/meeting-cards`. Regression suite (omega, admin exports, iter120-127): **54/54 pass**.


### Iteration 112 — Awards eligibility fixes + catalog ordering + Directory join year (2026-02-27) [FIX+ENHANCEMENT]
User reports: eligibility "Grant" buttons were resolving to the wrong award (Community Service → Ken Thompson; Member's → Life Membership), year selector only went 5 years back, Service Ribbon ignored the admin-set Year Joined, join year missing from Directory, and awards catalog needed a canonical order (or admin drag-rank).

- **Grant-target matcher fix (`pages/Admin.jsx::grant`)**: replaced case-insensitive `includes()` (substring) with exact-name-first + prefix fallback. Passed the fully qualified award names to `grant()` for Community Service Ribbon, Dr. Ken Thompson Distinguished Community Service Ribbon, and Member's Ribbon so "Community Service" no longer bleeds into "…Dr. Ken Thompson Distinguished Community Service Ribbon" and "Member" no longer resolves to "Life Membership Ribbon".
- **Year selector back to 2017 (`AwardEligibilityPanel`)**: dropdown now enumerates `currentYear+1` down to `2017` (previously stopped at `currentYear − 5`).
- **Service Ribbon uses `join_date` (`routes/awards.py::streak_start_year`)**: streak start now priority-chains `status_history` reactivation date → `join_date` (from the admin Member Card) → `created_at`. So members whose account was created after their actual induction still get the correct 1st/5th/10th year streak.
- **Directory shows Year Joined (`pages/Directory.jsx`)**: added a `Joined YYYY` line to each member grid card and the profile-dialog "Joined MMM d, yyyy" now reads `join_date || created_at`.
- **Awards catalog ordering**:
  - Backend `routes/awards.py`: new `sort_order` field on awards. `award_out` returns it. `list_awards` sorts by explicit `sort_order` (falling back to a canonical AOP order via `_default_sort_for` — fuzzy match tolerates "Ribbon"/"Award" suffix drift and curly apostrophes). Full Access admins have a new `PUT /api/awards/reorder` endpoint that persists a client-supplied order (403 for Governor Manager).
  - Frontend `AwardsAdmin`: cards now show a `#N` rank prefix and ↑/↓ buttons (Full Access only) that call `/awards/reorder`. A **Reset to AOP default order** button pushes the canonical order specified by the user (Life Membership → Federation Ribbon). Public `/awards` catalog respects the same order automatically.
- Verified end-to-end via curl + screenshots: catalog now lists Life Membership Ribbon → Federation Ribbon in the requested order; Governor Manager receives 403 on reorder; Directory cards + member-profile dialog both display the Year Joined.

### Iteration 111 — News multi-image + templates, News search, Governor auto-approve removal, Awards eligibility (2026-02-27) [FEATURE]
User request bundle: (a) News editor to support multiple images + layout templates (2/3 columns, image-beside-text, gallery, hero); (b) member-facing News search; (c) revoke auto-approve authority from Governor Manager admins; (d) show Full Access admins which members are eligible for each programme award (Service Ribbon, Fundraiser, Community Service, Dr. Ken Thompson, Recruitment, Member's, Chapter of the Year) using calendar-year criteria.

- **News multi-image + templates**:
  - `NewsIn` / `NewsUpdateIn` gained `images: List[str]` (max 5) and `template` Literal (`classic`, `two_col`, `three_col`, `image_left`, `image_right`, `gallery`, `hero`). `news_out` returns both.
  - `pages/NewsDetail.jsx` renders 6 distinct layouts via a `TemplateBody` component that splits body paragraphs across columns / interleaves images between chunks; single-column classic keeps its original behaviour.
  - Admin `NewsDialog` gained a **layout template** dropdown, an **Add photos (0/5)** multi-file uploader with per-image reorder (← →) and remove controls, and a live preview grid.
- **News search**: `GET /api/news?q=…` runs a case-insensitive escaped-regex `$or` across title / summary / body / tags. `pages/News.jsx` shows a rounded search input with 250 ms debounce and an explicit `news-empty` state for zero results.
- **Governor Manager can no longer auto-approve hours**:
  - `admin_log_hours`, `admin_log_hours_bulk`, and `admin_log_hours_csv` now flip the inserted docs to `status="pending"` (no `approved_at`/`approved_by`) when `is_chapter_scoped(admin)` — only Full Access admins produce auto-approved entries.
  - `PUT /hours/{id}/review` and `PUT /hours/{id}` both reject `status="approved"` for chapter-scoped admins with a clear 403 error message. Rejecting or leaving pending remains allowed.
- **Awards eligibility (Full Access only)**:
  - New `GET /api/awards/eligibility?year=YYYY` in `routes/awards.py`. Enforced via `admin_role_of(admin) == "full"` (403 for Governor Manager, Membership Manager, or any custom-scoped admin). Computes:
    - **Service Ribbon** — 1st complete active year, then every 5th year. Streak start uses the most recent `status="active"` entry in the new `status_history` audit list (falls back to `created_at`).
    - **Fundraiser Ribbon** — top 5 by summed completed-donation `amount` in the year.
    - **Community Service Ribbon** — members with ≥ 100 approved volunteer hours in the year.
    - **Dr. Ken Thompson Distinguished CS** — top member per chapter by weighted approved hours: `0.90 × AOP + 0.05 × Trendsetters + 0.05 × Other`.
    - **Recruitment Ribbon** — top 5 recruiters by count in the year.
    - **Member's Ribbon** — union of top-3 in each of hours / recruits / fundraising, ranked by how many categories the member appears in.
    - **Chapter of the Year** — score = `(recruits + hours + donors + checkins) / max(1, current_member_count - year_recruits)`.
  - `routes/members.py::set_member_status` and `routes/members_admin.py::admin_update_member` now append a `{status, at, by, by_name}` entry to `users.status_history` whenever an admin changes `status_override` — powers the Service Ribbon streak logic.
- **Admin Awards tab**:
  - New **AwardEligibilityPanel** below the awards grid, visible only when `user.admin_role === "full"`. Includes a year picker (current + 1 through current − 5), refresh button, six per-award cards, and a Chapter of the Year composite table. Every candidate row has a one-click **Grant** button that matches the appropriate award by name substring and calls `POST /awards/{id}/grant` with an auto-generated reason.
- **Tests**: `tests/test_iteration111_news_hours_awards.py` → 17/17 pass. Covers news template/images round-trip, search filter behaviour, Governor Manager pending + 403 paths, Full admin auto-approve regression, eligibility endpoint access control, and all seven eligibility keys.

### Iteration 110 — Hours: add "Trendsetters Spirits Event" event type (2026-02-27) [ENHANCEMENT]
User request: "For the Hours, under the 'Event Type', add 'Trendsetters Spirits Event'."

- **Backend (`models.py`)**: Extended the 5 `Literal` unions on hours-related Pydantic models (`HoursLogIn`, `AdminHoursLogIn`, `AdminHoursBulkLogIn`, `AdminHoursReviewIn`, `AdminHoursEditIn`) to include `"trendsetters_spirits"`.
- **Backend (`routes/hours.py`)**: CSV bulk-import validator now accepts `trendsetters_spirits` in addition to `aop_related` / `other`.
- **Frontend (`pages/Hours.jsx`)**: Added the new option to both Select dropdowns (member log form + admin edit) and taught the badge renderer to display "Trendsetters Spirits" (with `bg-secondary/20` accent) instead of falling through to "Other".
- **Frontend (`pages/Reports.jsx`)**: Added "Trendsetters Spirits" to the event-type filter chip row on the Reports → Hours tab.
- **Frontend (`pages/Admin.jsx`)**: Admin review-queue badge shows "Trendsetters Spirits" for entries with the new type.
- **Verified**: e2e API POST + UI screenshot confirmed the option appears in the "Log volunteer hours" modal and entries render with the new badge.

### Iteration 109 — Immediate video-meeting notifications (email + toast + chime + bell) (2026-02-27) [FEATURE]
User request: "When a member opens a video chat, can members receive notification by email immediately + ping?" (Clarified: Email + Toast + Chime + Bell.)

- **Backend (`routes/chat.py::start_video_meeting`)**:
  - Sends an immediate transactional email (via `send_bulk_email`, tag=`video_meeting`) to every OTHER conversation member (skips starter, skips opt-outs). Subject: "📹 {starter} started a video meeting in {conv_name}". Body includes a "Join the meeting" CTA linking to the Jitsi URL.
  - Broadcasts a dedicated `meeting:notify` WebSocket event `{ type, conversation_id, conversation_name, meeting_url, started_by_id, started_by_name, message_id }` — sent to every non-starter member on any page (not just `/chat`).
- **Frontend (`components/GlobalChatNotifier.jsx`)** — mounted once at the app root in `App.js` for authenticated users:
  - Opens a persistent WebSocket to `chatWsUrl()` and auto-reconnects with a 3s backoff on close.
  - On `meeting:notify`: (1) shows a sonner `toast.custom` card with `data-testid="meeting-notify-toast"` including "Open chat" + "Join" buttons, (2) plays a short embedded WAV chime (autoplay-blocked-safe), (3) dispatches an `aop:meeting_ping` window CustomEvent so any bell/badge listener can increment, (4) fires a browser `Notification` when permission was previously granted.
  - Requests `Notification.requestPermission()` once per session on mount.
- **Tests**: `tests/test_iteration109_video_meeting_notify.py` — 3/3 pass (start-meeting fans out email, `last_message_preview` reflects the meeting, and opt-out members are silently skipped without breaking the endpoint).
- **Frontend UI verified**: end-to-end screenshot flow confirmed that a jordan session logged into `/` sees the toast fire when maya starts a meeting (`meeting-notify-toast`, `meeting-notify-open-chat`, `meeting-notify-join` all present).


### Iteration 108 — Email composer: CTA buttons, linked images, dividers, merge tags (2026-02-27) [FEATURE]
User request: "In the admin email, allow admins to add buttons with embedded links. Allow adding photos / images with embedded links. Allow other cool things to make it easier and simpler to send emails."

- **CTA button** — new `components/EmailButton.jsx` custom TipTap node (`atom: true`) that:
  - Renders in-editor as a red pill with white text, click-to-select, and a floating toolbar (Label / URL / L·C·R align / × remove).
  - `renderHTML` emits an email-safe `<a data-email-button="1" style="…inline styles…">` inside a `<div style="text-align:…">` — bypasses the standard Link mark so styles aren't stripped.
  - Parses round-trip from either the editor or a re-loaded draft.
- **Linked images** — `components/ResizableImage.jsx` gained a `link` attribute + a Link² button in the floating image toolbar. When set, `renderHTML` wraps the `<img>` in an `<a href target=_blank rel=noopener style="text-decoration:none;display:inline-block">`. Parsing looks for a wrapping `<a[href]>` on load so links persist.
- **Divider** — `components/EmailHorizontalRule.js` overrides StarterKit's plain `<hr>` with a styled email-safe variant (`border-top:1px solid #e2e8f0;margin:20px auto;max-width:80%`).
- **Merge tags menu** — new toolbar dropdown (tag icon + "MERGE" label) that inserts `{{first_name}}`, `{{last_name}}`, `{{name}}`, `{{email}}`, or `{{line_name}}` at cursor. Backend `render_variables` already substitutes these at preview + send time — the UI just makes them discoverable.
- **Toolbar additions**: mouse-pointer icon (Insert CTA button) + horizontal-minus icon (Insert divider) between the image and undo/redo buttons.
- **Tests**: `tests/test_iteration108_email_composer.py` — 5/5 pass. Covers button style survival, HR survival, linked-image survival, merge-tag substitution, and HTML-escaping safety through the `/email/preview` pipeline.

### Iteration 107 — Video meeting live participant indicator (2026-02-27) [ENHANCEMENT]
User request: "show an indicator who's in the meeting. But when the meeting is over, stop the 15 second updates."

- **Backend (`routes/chat.py`)**:
  - New `db.meeting_participants` collection: `{meeting_id, conversation_id, user_id, user_name, avatar_url, joined_at, last_seen_at, left_at}`. Composite upsert on `(meeting_id, user_id)`.
  - `POST /meetings/{mid}/heartbeat` (optional `?left=true`) upserts the record and refreshes `last_seen_at`.
  - `GET /meetings/{mid}/participants` returns `{active, count, is_over, any_ever_joined, meeting_id}`. "Active" = `last_seen_at` within 30s (2× the client's 15s cadence) AND `left_at is null`. `is_over = any_ever_joined AND count == 0`.
  - Both endpoints enforce membership on the parent conversation (outsiders get 404).
  - Every heartbeat pushes a `meeting:update` event over the existing WebSocket so cards refresh near-instantly for other members (in addition to their own polling fallback).
- **Frontend (`pages/Chat.jsx`)**:
  - `VideoMeetingCard` polls `/meetings/{id}/participants` every 15s and renders:
    - Up to 4 stacked avatars + "+N more" overflow chip when >4 participants are live
    - A pulsing red "live" dot when count > 0
    - Status text: "N in meeting" / "Waiting for members to join" / "Meeting ended"
    - Button state: green **Start / join** when 0 live, red **Join meeting** when live, greyed **Meeting ended** disabled state when `is_over`.
  - **Polling stops** the moment `is_over === true` — `useEffect` short-circuits and the interval is cleared. Reload/subscription needs no re-render since the state persists.
  - `VideoMeetingModal` sends its own heartbeat every 15s while open + a `left=true` heartbeat on close so is_over flips promptly (no 30s stale-timeout wait).
  - Top-level `Chat` component forwards the WebSocket `meeting:update` event to a global `chat:meeting_update` browser event; cards react to it for instant updates.
- **Tests**: `tests/test_iteration107_meeting_participants.py` — 7/7 pass. Covers empty→heartbeat→multi-user→everyone-leaves→is_over transition + outsider 404s + missing-meeting 404. Regression: iter104 (6) + iter105 (13) + iter107 (7) = 26/26 green after the retest run.

### Iteration 106 — Chat: embedded Jitsi video modal (2026-02-27) [ENHANCEMENT]
User request: "want an in-app embedded Jitsi player (iframe modal) instead of a new-tab redirect."

- **Change**: replaced the "opens in new tab" flow (iter104) with a fullscreen in-app modal driven by a global controller. Now clicking **Start video meeting** or **Join meeting** opens the same `<Dialog>` — no context switch, still on the AOP site.
- **`VideoMeetingModal`** (`pages/Chat.jsx`):
  - Mounted once at the Chat page root so any component can trigger it via `openMeetingModal(meeting)` (avoids prop-drilling).
  - Iframe loads `${meeting.url}#config.prejoinPageEnabled=false&config.disableDeepLinking=true` — skips Jitsi's pre-join screen and suppresses the mobile-app deep-link banner.
  - `allow="camera; microphone; fullscreen; display-capture; autoplay; clipboard-write"` delegates full A/V + screen-share capability to Jitsi.
  - Header: room label + **Open in new tab** escape hatch (desktop only) + **Leave** button. Sizing: full-viewport on mobile, ~85vh × 5xl on desktop with rounded corners.
- **`VideoMeetingCard` / `StartVideoMeetingButton`**: `Join meeting` is now a `<button>` calling `openMeetingModal(meeting)`; starter flow also opens the modal in-place (no `window.open`). Card footer copy updated to "Powered by Jitsi · opens in-app".
- **No new backend changes**: same `POST /conversations/{cid}/video-meeting` endpoint from iter104 — iframes just consume the URL it already returns.
- **Regression**: iter104 (6/6) + iter105 (13/13) still green. Playwright smoke confirmed modal opens, iframe loads Jitsi with correct permissions, and Leave closes cleanly.

### Iteration 105 — Chat group admins + creator-controlled add-members policy (2026-02-27) [FEATURE]
User request: "Allow creator of group to make members admins in the group chat, and allow the creator and admins to add and remove members from the groups." + "Also allow creator to choose whether regular members can add members to a group."

- **Backend (`routes/chat.py`)**:
  - Every group conversation now stores `admin_ids: List[str]` (creator is *implicit*, extras go here) and `member_add_policy: "admins_only" | "anyone"` (default `admins_only`).
  - `ConversationUpdateIn` gains `promote_ids`, `demote_ids`, `member_add_policy`.
  - `update_conversation` permission matrix:
    - **Creator (or site-admin)**: full control — rename, promote/demote, add/remove, toggle policy.
    - **Group-admins** (in `admin_ids`): add + remove members, but cannot promote/demote or toggle policy.
    - **Regular members**: cannot add unless `member_add_policy=="anyone"`; cannot remove.
    - **DM special case**: any DM party can add — that call auto-promotes the chat to a group (existing iter104 behavior preserved).
  - Guardrails: creator can't be demoted or removed; only members can be promoted (400 otherwise); removing a group-admin auto-strips them from `admin_ids`; leaving a group as a group-admin auto-strips as well.
  - `conversation_out` returns the new `admin_ids` + `member_add_policy` for the frontend to render badges + toggle.
- **Frontend (`pages/Chat.jsx`)**:
  - New `MemberRow` component: shows **Creator** pill (red) or **Admin** pill (amber) per member; creator sees a **Make admin / Remove admin** button per non-creator, non-self member; creator + group-admins see a small **X** to remove.
  - Creator-only "Who can add members?" toggle inline in settings — flips `member_add_policy` between `admins_only` and `anyone` with toast confirmation.
  - `AddMembersDialog` button is now gated: visible on DMs, and on groups only when the viewer is creator/admin OR the policy is `anyone`.
- **Tests**: `tests/test_iteration105_chat_group_admins.py` — 13/13 pass. Full matrix covered including site-admin-added-then-moderates flow. iter104 regression: 6/6 green.

### Iteration 104 — Chat: add members mid-thread + video meetings via Jitsi (2026-02-27) [FEATURE]
User request (choices 1c, 2a, 3c): "Allow members to be added to a chat and groups after the chat messages have already began. Allow video meeting in the chat."

- **Add members to existing chats** (`routes/chat.py::update_conversation`):
  - Group chats: `PUT /conversations/{cid}` with `add_member_ids` now supports adding to groups **and** DMs.
  - **DM → group auto-promotion**: adding any 3rd participant flips `type` from `"dm"` to `"group"` while preserving the entire message history.
  - `remove_member_ids` is still group-only (DMs must be left via `POST /conversations/{cid}/leave`, or use `DELETE` if you created it).
  - Frontend: new `AddMembersDialog` inside `ConversationSettings` on every chat (DM + group). Shows an amber "This will convert your DM into a group chat — history preserved" notice on DMs.
- **Video meetings** (Jitsi Meet):
  - New backend endpoint `POST /conversations/{cid}/video-meeting`. Generates a fresh `https://meet.jit.si/aop-{convslug}-{uuid-hex}` room per call (unique per launch so old links can't be reused), and posts it into the chat as a message with `kind="video_meeting"` and a `meeting` object (`url`, `room`, `started_by`, `started_by_name`, `started_at`).
  - `message_out` now returns `kind` and `meeting` fields on every message (backwards compatible — legacy rows default `kind="text"`).
  - Frontend: new **Video** icon in the thread header (`start-video-meeting-btn`). Clicking it (a) posts the meeting card to the chat via WebSocket so every member sees it in real time, (b) opens the Jitsi room in a new tab for the starter, and (c) toasts confirmation.
  - Every video-meeting message renders as a **full-width actionable card** (`VideoMeetingCard`): header shows starter + timestamp, prominent red **Join meeting** button, "Powered by Jitsi · opens in new tab" footer. Non-text kinds bypass the standard bubble path so they visually stand out.
- **Tests**: `tests/test_iteration104_chat_addmembers_video.py` — 6/6 pass. Covers add-to-group, DM auto-convert (with history preservation), DM remove-forbidden 400, meeting posts with correct URL shape, unique room per call, and 404 on non-member conversation.
- **No new integrations required**: Jitsi Meet is free, self-hosted at meet.jit.si, no API key, no account. Works on any browser/device.

### Iteration 103 — RSVPs report includes walk-in check-ins (2026-02-26) [BUG FIX]
User bug: "I created an event that has passed. I checked members in so I can track who went, but when I check in the admin reports → RSVPs → and filter by 'Event date', nothing comes up for the past event. I want the 'Checked In' count to work regardless of an RSVP."

- **Root cause**: `/api/reports/rsvps` iterated `db.rsvps` only. Members who were checked in without an RSVP never appeared, so an event whose entire attendance was walk-in-only looked empty.
- **Fix (`routes/reports.py`)**: after building the RSVP-based rows, union in `db.checkins` records where `(event_id, user_id)` isn't already represented. Each becomes a row with `is_walk_in=True`, `rsvped_at=None`, and a synthetic `rsvp_id="walkin-{event_id}-{user_id}"` (guests are excluded — they still ride under their host's RSVP row).
  - Walk-in scope respects the same event / period / chapter filters as the RSVP branch. When `date_field=rsvped_at` (default) and no event scope is set, walk-ins are bounded by `checked_in_at` so we don't sweep unrelated events into the period.
- **Fix (summary counts)**: `rsvp_count` no longer counts walk-ins (they didn't RSVP). New `walk_in_count` total. `checked_in_count` still counts every row with `checked_in_at`. Per-member, per-chapter, and per-period aggregations honor the same split. Period buckets pick `checked_in_at` for walk-ins when the toggle is RSVP-date so past attendance still surfaces on "By period".
- **Frontend (`pages/Reports.jsx`)**: Totals card grew to 4 tiles (RSVPs / Walk-ins / Guests / Checked in). Individual-entries table shows a yellow **Walk-in** pill in the RSVPed column when `is_walk_in`.
- **Tests**: `tests/test_iteration103_rsvp_walkins.py` — 4/4 pass. Regression: iter102 (12) + iter103 (4) = 16/16 green.

### Iteration 102 — Member Recruitment tracking (2026-02-26) [FEATURE]
User request: "Create tracking for Member Recruitment. Make an admin tab for recruitment to track members who recruited members currently in the organization. Have the tab track an admin report exactly like the RSVPs, Hours, and Donations tabs. Allow admin to upload a csv file to track recruitment. In addition, make a top Member Recruitment Leader Board on the home page just like the other leader boards."

- **Data model** (`db.recruitments` collection): `id`, `recruiter_id`+`recruiter_name`+`recruiter_email`, `recruit_id`+`recruit_name`+`recruit_email`, `chapter_id`+`chapter_name` (from recruiter, denormalized), `date_recruited` (ISO), `notes`, audit fields (`created_by`/`updated_at`). Denormalized names/emails/chapter avoid $lookups on list + report + leaderboard queries.
- **Backend module** (`/app/backend/routes/recruitment.py`, ~470 lines) exposes:
  - Admin CRUD: `GET /recruitments` (w/ `q=` search), `POST /recruitments`, `PUT /recruitments/{rid}`, `DELETE /recruitments/{rid}` — all behind `admin_tab_dep("recruitment")`.
  - Guards: `recruiter_id == recruit_id → 400`, duplicate (`recruiter, recruit, date`) tuple → 409.
  - Chapter-scoped Governor Managers see only recruitments touching their chapter's members.
  - CSV: `/recruitments/csv/template` (header + example), `/recruitments/csv/export` (full-table download), `/recruitments/csv` (dry_run preview + commit). Member resolution: `email → full_name → first_last`; ambiguity is a hard error, duplicates are `SKIP` not `ERROR`.
  - Reports: `/reports/recruitment` (entries) + `/reports/recruitment/summary?group_by=recruiter|chapter|month` with year/period/chapter filters.
  - Homepage leaderboard: `/leaderboards/top-recruiters?period=q1..q4|year` returns top 5 chapters + top 5 recruiters, mirrors the top-donors shape.
- **Admin tab permissions**: `recruitment` added to all four admin_role tab sets (`full`, `membership_manager`, `operations_manager`, `governor_manager`) in `ADMIN_ROLE_TABS` (server.py) + the frontend mirror in `Admin.jsx`.
- **Frontend**:
  - `components/RecruitmentAdmin.jsx` — table w/ New/Edit/Delete + CSV Import/Export + per-recruit search. MemberSelect dropdown excludes the counterpart to prevent self-recruitment client-side.
  - `components/TopRecruitersLeaderboard.jsx` — Q1/Q2/Q3/Q4/{year} switcher + Top Chapters / Top Recruiters sub-tabs; matches the visual weight of `TopDonorsLeaderboard`.
  - `pages/Reports.jsx` — new `Recruitment` tab with 4 sub-views (Individual entries / By recruiter / By chapter / Monthly trend) + filters + CSV export + inline bar-chart for the monthly trend.
  - `pages/Home.jsx` — `TopRecruitersLeaderboard` inserted right below `TopDonorsLeaderboard`.
- **Seed fix**: `mm.tx@clubhaven.app` was drift-seeded as `role="member"` — corrected to `role="admin"/admin_role="membership_manager"` so future testing sessions can validate the Membership Manager access path.
- **Tests**: 12/12 pass in `tests/test_iteration102_recruitment.py` covering CRUD, self-recruit guard, duplicate 409, CSV template + email/name-fallback import + skip-duplicates + error rows, all report groupings, leaderboard period=q3 & year, and anonymous-access lockout. Frontend end-to-end also 100% via Playwright testing agent.

### Iteration 101 — Dues reminders: members receive emails; admin digest excludes Governor Managers (2026-02-26) [POLICY]
User first asked to send dues reminders only to Admins, then corrected: "exclude only governor managers receiving the reminders. I want members to continue receiving the emails."

- **Backend (`routes/automated_emails.py`)**:
  - `_send_dues_reminders`: continues to email each individual member at the 30d / 15d / 5d / +1d grace windows via `send_bulk_email`, honoring `email_opt_out` and `email_prefs.dues_reminders`.
  - `_send_admin_dues_summary`: eligible admin recipients narrowed to `admin_role in {None, "", "full", "operations_manager", "membership_manager"}`. Governor Managers (and any future admin sub-role) are explicitly excluded so they aren't spammed with digests unrelated to their scope.
  - Digest subject: `AOP dues reminders — N members to follow up on`.
  - Footer copy updated to reflect the new eligible-admin population.
- **Tests**:
  - Rewrote `tests/test_iteration101_dues_reminder_admin_only.py` (4 tests) — asserts members receive direct reminders, full/ops/membership managers receive the digest, governor manager excluded, and dedupe prevents re-sends within a cycle.
  - Fixed subject-format drift in `tests/test_iteration53_dues_admin_summary.py`.
- **Regression**: iter53 (6) + iter101 (4) all green.

### Iteration 100 — Governor Managers cannot change their own chapter (2026-02-26) [SECURITY]
User request: "Ensure that members coded as a Governor Manager (Admin) cannot change their chapter in their profile."

- **Context**: Iter99 opened up chapter self-service via `PUT /members/me` so plain members could pick their chapter. Governor Managers are chapter-scoped admins whose authority is tied to their assigned chapter — if they could self-reassign, they could silently migrate their admin scope without oversight. Only a full-access admin should be able to move them.
- **Backend (`server.py` `/members/me`)**: when the caller's `role="admin"` AND `admin_role="governor_manager"` AND the incoming `chapter_id` differs from the current value, respond with **HTTP 403** and detail "Governor Managers cannot change their own chapter. Ask a full-access admin to reassign." A no-op save (same chapter, other fields changed) still succeeds.
- **Frontend (`Profile.jsx`)**: for governor managers the chapter dropdown is replaced with a locked read-only display showing the current chapter name + a "Locked" pill and an inline explainer directing them to a full-access admin. Plain members and full admins still see the normal dropdown.
- **Admin path preserved**: `PUT /members/{user_id}/chapter` (admin-only) still works for full-access admins to reassign a governor's chapter — verified by regression test.
- **Tests**: `tests/test_iteration100_governor_chapter_lock.py` — **4/4 pass** covering: governor blocked with 403 on chapter change; governor can still edit other profile fields; full admin can still reassign; plain members retain self-service. Combined with iter99: **8/8 pass**.

### Iteration 99 — Members can self-assign their chapter (2026-02-26) [P0 BUG FIX]
User bug: "When the member selects their Chapter, it goes blank when they leave the profile page. However, the admin member 'Chapter' field may have a chapter selected."

- **Root cause**: `ProfileUpdateIn` had no `chapter_id` field, so the frontend Profile page routed chapter changes to `PUT /members/{user_id}/chapter` — an admin-only endpoint guarded by `admin_tab_dep("members")`. Every member's chapter selection returned 403 and silently discarded the change, leaving the on-screen field blank on the next load while the admin's Members list still reflected whatever chapter had been set previously.
- **Fix (`models.py`)**: added `chapter_id: Optional[str]` to `ProfileUpdateIn`.
- **Fix (`server.py` `/members/me`)**: validate `chapter_id` when present — must reference an existing chapter (400 "Unknown chapter" if not) or be empty to clear the assignment.
- **Fix (`pages/Profile.jsx`)**: removed the separate admin-endpoint call and just include `chapter_id` in the main `PUT /members/me` payload. Same path handles both set and clear.
- **Admin-side unchanged**: the admin `PUT /members/{user_id}/chapter` endpoint keeps its 403 gate for non-admins (verified by regression test).
- **Verified end-to-end**: member sets DMV → persists on `/auth/me` → admin's Members listing shows DMV → member clears it → cleared → unknown chapter rejected. Screenshot + curl round-trip both green.
- **Tests**: `tests/test_iteration99_member_chapter_self_assign.py` — **4/4 pass**. Combined regression with iter96+97+98: **25 pass, 1 skipped**.

### Iteration 98 — Homepage leaderboards support Q1-Q4 + year period switcher; no "All time" (2026-02-26) [FEATURE]
User asked to add a period selector to both homepage leaderboards allowing members to switch between quarters within the current year and the full year, and to remove the "All time" fallback that iter92.1 had added.

- **Backend** (`server.py` community-service + `routes/donations.py` top-donors):
  - Both leaderboard endpoints now accept `period ∈ {quarter, month, year, all, q1, q2, q3, q4}`.
  - Explicit-quarter shortcuts (`q1`-`q4`) target the named quarter of the **current calendar year** with an explicit end-date bound (`$gte` AND `$lte`) so Q1 data doesn't leak into later-quarter queries.
  - Existing `period=all` is preserved for admin reporting (still used by non-homepage callers) but the homepage never requests it.
- **Frontend** (`CommunityServiceLeaderboard.jsx` + `TopDonorsLeaderboard.jsx`):
  - New period switcher: 5 pill buttons — `Q1 · Q2 · Q3 · Q4 · <YYYY>` — where YYYY is the current calendar year, so admins never have to change the JSX at year rollover.
  - Default selection = current quarter (computed from `new Date().getMonth()`).
  - Removed the iter92.1 all-time fallback. If a period has no data the section still renders with a friendly empty-state ("No chapter donations for Q3 2026 yet.").
  - Subtitle + empty-state copy now interpolate `data.period_label` so the strings stay consistent when the user switches ("Approved volunteer hours for Q1 2026.", "Completed donations for 2026.").
- **Tests**: `tests/test_iteration98_leaderboard_periods.py` — **12/12 pass, 1 skipped** (no seed donations to cross-verify Q leakage). Verifies: each named period returns the expected `period_label` for both endpoints; Q1+Q2+Q3+Q4 chapter totals never exceed the year total (proves no data leakage); `period=all` still works at the API level for admin reporting.

### Iteration 97 — Personnel Data Brief download & preview fixes (2026-02-26) [P0 BUG FIX]
Four bugs the user reported in one shot:

- **Bug 1: Detailed PDF download was missing Personal Data + Organization sections.** They showed on-screen but not in the download. Added §I Personal Data (address, city, state, zip, country, birthdate, branch, marital, email, phone) and §II Organization (chapter, region, status, tier, role, joined, renewal, line name) as full data tables at the top of the detail attachment in `routes/reports.py`.
- **Bug 2: Assignment History section was always empty in the download.** Root cause: the code read `m.get("assignments")` (wrong key — the real field is `assignment_history`) and each entry was read with wrong sub-keys (`title`, `date_started`, `duties`) that don't exist on the schema. Fixed to read `assignment_history` and use the actual fields (`duty_title`, `chapter_name`, `rank`, `state`, `location`, `start_date`, `end_date`, `is_current`). Also added sort so current assignment appears first.
- **Bug 3: One-pager didn't fill the landscape page.** Bumped section-title font 9pt → 10.5pt, body/tile fonts 7.5pt → 8pt, row padding 1pt → 3pt (tiles) / 4pt/5pt (section bars), and added 4pt outer column padding. Result: content stretches to fill ~90% of the 8.5" vertical space (was ~55%). Pytest asserts it stays exactly 1 page on a landscape letter.
- **Bug 4: Preview screen showed empty navy bars instead of section titles.** Root cause was a **prop name mismatch** — `OrbTile` component destructured `title` but every caller passed `tileTitle`, so the label was `undefined` and the navy bar rendered blank. Also the Tailwind arbitrary values `bg-[hsl(220_45%_12%)]` + `text-white` were fragile against the `print:text-black` parent variant. Fixed both: accept either `title` or `tileTitle`, use inline `style={{ backgroundColor: "#0C1B33", color: "#FFFFFF" }}` so nothing can strip it, and added `print:!text-white` for safety. Verified via computed-style read: `color=rgb(255,255,255) bg=rgb(12,27,51)`.

**Tests**: new `tests/test_iteration97_personnel_brief.py` — 4/4 pass (§I/§II present in detail, assignment rows populated with all required fields, one-pager stays at 1 page + landscape dims, tile titles come through in the PDF text). Two pre-existing tests (`test_iteration30::test_brief_pdf_has_all_10_sections` and `test_iteration73::test_pdf_page1_landscape_and_orb_sections`) were failing BEFORE my changes — verified via `git stash` — they check for stale section names ("Personal Information") that were superseded when iter73 introduced the ORB layout.

### Iteration 96 — Sign-in activity log for full-access admins + auto-clear "Pending Password Setup" pill (2026-02-26) [FEATURE + BUG FIX]
User asked two things:
- "Allow full access Admins the ability to see sign-in activity from members and the pages they visited. Show the date and time logged in, and the pages visited, and the duration of login."
- "Re-look the members password setup. If they have logged in, please remove the 'Pending Password Setup' pill from their name on the admin members tab."

**Sign-in activity tracking:**
- New `routes/login_activity.py` registers a `login_activity` Mongo collection.
- `POST /api/activity/page-view {path}` — authenticated. Frontend pings whenever a route changes. Attaches to the user's most-recent open session (within 8 h idle window) or starts a new one tagged `started_via=page_view` (covers cookie-refresh sessions without an explicit /auth/login).
- `GET /api/admin/login-activity?limit=200&user_id=...` — admin-only listing with computed `duration_seconds` and `pages_count`. Bulk listing omits the full `pages_visited` to keep payload small.
- `GET /api/admin/login-activity/{session_id}` — full detail with `pages_visited` array.
- Hooked into `routes/auth.py`:
  - Successful `/auth/login` calls `record_login_session(user, request)` — captures IP, user-agent, login_at.
  - `/auth/logout` calls `record_logout(user_id)` which stamps `logout_at` on the user's MOST RECENT open session (sorted by login_at desc, then update by id — Mongo's `update_one` doesn't accept sort).
- New `components/PageActivityTracker.jsx` mounts inside the BrowserRouter and pings `/activity/page-view` on every navigation (800 ms debounce, guarded by `useAuth().user` so guests are never tracked). Silent on errors so a failed ping never blocks navigation.
- New `components/SignInActivityAdmin.jsx`: sortable table (Member, Login ET, Duration, Pages, IP, Browser, Status) with chevron-expandable rows showing the full path list + per-page timestamps. Tab is gated on `perms.admin_role === "full"` so only full-access admins see it.

**"Pending Password Setup" pill bug:**
- Root cause: iter78 had explicitly kept the pill flag set even after login on the cautious assumption that bulk-imported members might still need to go through `/set-password`. User pushback: "if they have logged in, remove the pill."
- Fix in `routes/auth.py`: a successful `/auth/login` now `$unset`s `pending_set_password` if it was set. The flag persists for invited members who never log in.
- Boot-time reconciler `reconcile_pending_set_password` was inverted: it now CLEARS the flag for anyone who has either consumed a `/set-password` token OR has any document in `login_activity` (i.e. proves they've actually used the app). Logs "cleared pending flag for N member(s) who have logged in" so the audit trail is visible.

**Tests** (`tests/test_iteration96_signin_activity.py`):
- `test_login_records_session_and_logout_stamps_duration` — full happy path: login → page-views → logout → admin sees the session with duration + pages_count.
- `test_admin_can_pull_session_detail_with_full_page_list` — `GET /admin/login-activity/{id}` returns the `pages_visited` array with `{path, at}` entries.
- `test_non_admin_cannot_pull_activity` — 403 for a member token.
- `test_page_view_requires_auth` — 401 with no token.
- `test_successful_login_clears_pending_set_password_flag` — set the flag via Mongo, login, verify flag is unset.
- 5/5 pass. Combined with iter93+94+95 regression: **20/20 pass**.

### Iteration 95 — Members self-select their branch of service (2026-02-26) [FEATURE]
User asked: "Allow members to select their branch of service using Army / Air Force / Marine Corps / Navy / Coast Guard / Space Force. Once they select, update the admin members Branch section."

- **Shared constant** (`/app/frontend/src/lib/militaryBranches.js`): canonical 6-branch list (Army → Air Force → Marine Corps → Navy → Coast Guard → Space Force, DoD seniority order).
- **`Profile.jsx`**: added a "Branch of service" `<Select>` in the same row as Chapter. Persisted via the existing `PUT /api/members/me` endpoint (`ProfileUpdateIn.branch_of_service` was already in the model, just unwired on the form). "— Not specified —" option clears the field. Legacy non-canonical values (e.g. "Marines", "USAF") render in the dropdown with a `(legacy)` label so editing doesn't silently wipe them.
- **`Admin.jsx`**: replaced the free-text "Branch of service" `<Input>` with the same dropdown in BOTH the "New member" and "Edit member" dialogs. Admin overrides still write to the same `branch_of_service` field, so the data is unified — members and admins now edit the same value with the same constraints.
- **Tests**: new `tests/test_iteration95_branch_of_service.py` — **8/8 pass** (one round-trip per canonical branch + clear-to-empty + legacy free-text value still accepted by the backend).

### Iteration 94 — Event times stay in Eastern Time + sub-event delete is permanent (2026-02-26) [P0 BUG FIX]
User reported two bugs: "If I put 6 pm as the start time, it needs to stay at 6 pm. All of the tickets have the incorrect time" and "When I delete a sub-event, ensure it stays deleted."

**Bug A — Times silently shifted by the admin's browser timezone:**
- Root cause: `<input type="datetime-local">` returns a naive `YYYY-MM-DDTHH:mm` string and the code did `new Date(localStr).toISOString()` — which the browser interpreted in the ADMIN'S local timezone. An admin in Texas (CT) typing 6:00 PM stored 6:00 PM CT (= 00:00 UTC next day) which then rendered as 7:00 PM Eastern on the ticket. The user wants all event times anchored to Eastern Time regardless of who's editing.
- Fix (frontend, `lib/eventTime.js`): added `etInputToUtc(localStr)` and `utcToEtInput(iso)` helpers wrapping `date-fns-tz`'s `fromZonedTime` / `formatInTimeZone`. They interpret the input as ET wall-clock and round-trip pre-fills.
- Fix (frontend, `Admin.jsx` + `EventDetail.jsx`): swapped every `new Date(...).toISOString()` and `.slice(0, 16)` site to use the helpers. Added "(Eastern Time)" labels next to every datetime-local input so admins know explicitly.
- Fix (backend, `routes/rsvps.py`): the ticket email's `when` string previously rendered `%I:%M %p UTC` — now converts to `America/New_York` via `zoneinfo.ZoneInfo` and renders `06:00 PM EST` / `06:00 PM EDT` automatically. Applied to both the member combined-ticket email AND the new per-guest ticket email.
- Verified end-to-end: admin enters 6:00 PM ET → stored as `2027-01-15T23:00:00Z` → ticket email renders "Friday, Jan 15, 2027 · 06:00 PM EST". Test asserts `06:00 PM` + `EST` after round-trip.

**Bug B — Deleted anniversary sub-events resurrected on backend restart:**
- Root cause: `seed_anniversary_subevents()` re-inserted any of the 5 canonical sub-events ("Sip & Paint", "Sneaker Ball Banquet", "Top Golf", "Transportation to Sip & Paint", "Transportation to Top Golf") if they were missing — running on every startup. So when an admin deleted one, the next worker restart silently brought it back.
- Fix (`routes/events.py` DELETE): when the deleted event is a canonical anniversary sub-event under the 10-Year Anniversary parent, write a tombstone document `{title, parent_title, deleted_at}` into a new `deleted_default_subevents` collection (same pattern as `deleted_default_albums` and `deleted_builtin_automated_emails`).
- Fix (`server.py` seeder): `seed_anniversary_subevents` now loads the tombstone set first and skips any tombstoned title in the reconcile loop. Idempotent — tombstone survives across restarts.
- Verified: deleted "Sip & Paint" → restarted backend → "Sip & Paint" stays gone. Tombstone doc inspected directly in Mongo confirms `parent_title: "Alpha Omega Phi 10-Year Anniversary"` and `deleted_at` ISO timestamp. After cleanup the canonical event is restored.

**Tests**: new `tests/test_iteration94_et_time_and_subevent_tombstone.py` — 2/2 pass (ET round-trip + tombstone survives reseed). Combined regression with iter93 + photos suite: **18/18 pass**.

### Iteration 93 — Admin can add guests to an existing member's RSVP + per-guest ticket emails (2026-02-26) [FEATURE]
User asked: "Allow admins to add guests to members' event tickets if they already RSVP'd. Also ensure guests get an email of their tickets if the admin inputs their email address."

- **New endpoint `POST /api/events/{event_id}/rsvps/{user_id}/guests`** (`routes/rsvps.py`):
  - Admin-only. 404 if the member hasn't RSVP'd yet (use `/admin-rsvp` instead). 400 if the guest list is empty or every entry is missing a name.
  - Each new guest gets a uuid `ticket_id`, `added_by_admin` / `added_by_admin_name` / `added_at` attribution stamps, and an optional `email`.
  - Capacity-guarded: the new guests are validated against the event's seat cap before being appended.
- **Per-guest ticket email**: extended `send_rsvp_ticket_email` so that any guest with an `email` field also receives a personal ticket email (containing just THEIR QR + event details + who added them). Idempotent via a per-guest `email_sent_at` stamp — re-running the helper after a guest-list edit does not re-spam already-emailed guests. The member still gets their unified "all tickets in one email" copy.
- **Frontend `AdminManageRsvpsDialog.jsx`**:
  - Each member row now has an **"Add guest"** button next to the existing "Un-RSVP".
  - New `AddGuestDialog` sub-component: name (required), email (optional with inline explainer that the guest gets their own QR if provided), ticket-type dropdown (general/guest/vip/all_access/volunteer/speaker), and a "send refreshed email" toggle.
  - The dialog shows the host member's name in the title ("Add a guest for Riley Chen") so admins don't get confused when triaging multiple members.
  - Guests that have an email on file now show their address inline in the existing-guest list, with a ✓ once the personal ticket has been sent.
- **Tests**: new `tests/test_iteration93_admin_add_guests.py` — **5/5 pass** (happy path, non-admin 403, no-RSVP-yet 404, empty guest list 400, audit-trail + email-field persistence).

### Iteration 92.1 — Real root cause: sync object-storage I/O blocking event loop (2026-02-26) [P0 BUG FIX]
After redeploying iter-92, the user re-reported "Same login error after trying to upload a photo." Iter-92's frontend-only fix moved uploads off the bulk endpoint but **a deeper backend bug was still in play**:

- **Root cause**: `put_object` and `get_object` use synchronous `requests` calls (network round-trip to Emergent object storage) and were invoked DIRECTLY inside `async def` FastAPI handlers. Each upload blocked the event loop for the full network duration. While that worker was blocked, **no other request could be served** — including the user's own `/auth/me` refresh fired by the auth interceptor → it timed out → looked like a logout → Cloudflare's idle-connection page showed up.
- **Symptoms it explains**: "logged out after upload", "Cloudflare login error", `/auth/me` hanging, the page going blank during multi-file uploads, photo grid being slow to load while other requests were in flight.
- **Fix**: wrapped all hot-path object-storage calls in `asyncio.to_thread(...)`:
  - `routes/photos.py POST /api/photos` — single upload (the one the new sequential UploadButton uses).
  - `routes/photos.py POST /api/photos/bulk` — legacy bulk endpoint (still wrapped for safety in case old clients hit it).
  - `server.py GET /api/files/{storage_path}` — photo proxy (used by every `<img>` in the grid + lightbox).
  - `routes/photos.py POST /api/photos/download-zip` — already wrapped in iter-92.
- **Verification**: concurrent test (2× 5MB upload + 1× `/auth/me`) — `auth/me` returned in **135 ms** while uploads finished in **852 ms each**. Total wallclock **868 ms**. Before the fix, `auth/me` would have queued behind the uploads for ~1.7 sec.
- **iPhone HEIC support**: also extended `IMAGE_EXT` to include `heic/heif`, added matching MIME types, and the single-upload endpoint now also accepts files whose extension is missing but whose `Content-Type` starts with `image/` — iPhones strip extensions for HEIC and would have been rejected with HTTP 400.
- **Tests**: photo regression suite (`test_iteration82` + `test_iteration90`) — **11/11 pass**. HEIC uploads verified end-to-end (both by `.heic` extension and by `Content-Type: image/heic` alone).

### Iteration 92 — P0 Photos Production Bug Cluster (2026-02-26) [P0 BUG FIX]
User-reported production bugs in the Photos page; all four fixed and end-to-end verified on the preview URL.

- **Bug 1: Hard-refresh inside an album kicked user back to /photos.**
  - Root cause: active-album state lived only in component state; a reload reset it to `null`.
  - Fix: `App.js` now registers `/photos/:albumId` alongside `/photos`. `Photos.jsx` uses `useParams() + useNavigate()` so the URL is the source of truth for the open album. A reconcile-effect waits for the album list to load, matches the URL `:albumId` to an album, and redirects with `replace: true` if the id is stale.
- **Bug 2: Multi-photo upload crashed → forced logout → "Cloudflare parse error" on next login.**
  - Root cause: `POST /api/photos/bulk` accepted up to 100 MB in a single multipart payload — Cloudflare/edge ingress drops anything over ~100 MB with a 413/520, severing the connection during the response. The single hung request appeared to the React app as a generic 500 and the auth-context refresh logic ran headlong into a half-broken socket, which on Safari/iOS surfaces as the "Cloudflare HTML parse error" the user reported.
  - Fix: `Photos.jsx UploadButton` was rewritten to send files **one at a time** via the single-photo `POST /api/photos` endpoint (each file ≤10 MB, well under any proxy limit). Each upload is independent — a single failure no longer aborts the batch or touches auth state. The button now shows `Uploading 3/7…` per-file progress and awaits the parent `loadPhotos` refresh before clearing the busy label so freshly uploaded photos appear inline.
- **Bug 3: Album zip download timed out / corrupted if user clicked away.**
  - Root cause: `download_photos_zip` built the entire archive in a `BytesIO` before returning, blocking the event loop and holding the whole zip in RAM. Large albums hit Cloudflare's ~100-second response-start timeout because no bytes were sent until the zip was fully built.
  - Fix: switched to `tempfile.SpooledTemporaryFile(max_size=50 MB)` (spills to disk past the threshold) and an `async`-iterator `StreamingResponse` that yields 64 KB chunks. The zip is built in a worker thread (`asyncio.to_thread`) so the event loop can keep serving other requests during a big archive.
- **Bug 4: Logout had noticeable latency.**
  - Root cause: `AuthContext.logout` `await`-ed `POST /auth/logout` before clearing local state, so any slow round-trip blocked the UI for hundreds of milliseconds.
  - Fix: clear tokens + flip `setUser(false)` **first**, then fire `api.post("/auth/logout")` with `.catch(() => {})` — true fire-and-forget. Measured UI transition ≈120 ms in iteration_90 testing.
- **Testing**: `testing_agent_v3_fork` iteration_90.json — all four fixes verified on the live preview URL (refresh + 3-file upload + zip download + nav menu → logout), 100% pass, no critical issues. Backend regression: `test_iteration82_photos_module_and_quick_checkin` + `test_iteration90_photo_cache_and_email_multi` — **11/11 pass**.

### Iteration 91 — Overdue-dues Zeffy URL for inactive members (2026-02-26) [FEATURE]
- **Inactive members now see the renewal-overdue Zeffy link** instead of the standard dues link, automatically.
- **`routes/payments.py`**:
  - New `ZEFFY_OVERDUE_URL = "https://www.zeffy.com/en-US/ticketing/aop-membership-renewal-overdue-dues"` (env-overridable via `ZEFFY_OVERDUE_URL`).
  - `_is_inactive_for_dues(user)` returns true when `status_override == "inactive"` OR `auto_inactivated_at` is set (the grace-period reaper auto-inactivation path).
  - `GET /api/payments/zeffy/config` now returns the overdue URL for inactive members and includes a new `is_overdue: bool` field so the UI can label the CTA differently if needed.
  - Both dues-payment paths (auto-approve via `trust_zeffy` and admin-approve via `PUT /transactions/{id}/approve-zeffy`) now clear `status_override="inactive"` + `auto_inactivated_at` and stamp `reactivated_at` (+ `reactivated_by` on admin-approve) so the normal Zeffy URL returns automatically on the next config fetch.
- **`server.py`**: extended the inactive-member API whitelist to include `/api/payments/zeffy/` (config + confirm + validate) and `/api/me/transactions` — otherwise inactive members couldn't reach the very endpoints needed to reactivate themselves.
- **Frontend**: zero changes needed — `ZeffyCheckout` already pulls the URL from `/payments/zeffy/config`, so the swap is automatic.
- **Tests**: new `tests/test_iteration91_overdue_dues_url.py` — **5/5 pass** (default member sees normal URL, status_override path triggers overdue URL, grace-reaper path triggers overdue URL, admin-approve clears flag + restores normal URL, auto-approve clears flag + restores normal URL). Payments regression suite re-run: **27/27 pass**.

### Iteration 90 — Photo loading perf + Email multi-select & external recipients (2026-02-26) [FEATURE]
- **Photo loading speed**: three layered fixes addressing the user-reported slowness.
  - MongoDB indexes added: `photos.album`, `photos.storage_path`, `(album, created_at)` — the album-list aggregation + file-proxy lookups go from collection-scan to indexed.
  - `/api/files/{storage_path}` proxy (`server.py`) now emits `Cache-Control: private, max-age=31536000, immutable` + a stable `ETag` (storage paths are uuid-stamped, hence immutable). Repeat hits with `If-None-Match` short-circuit to **304 Not Modified** with no object-storage round-trip and no body bytes — verified via curl.
  - `Photos.jsx` thumbnails now use `<img loading="lazy" decoding="async">` so below-the-fold albums + photos don't all download at once.
- **Email composer — multi-select members + external recipients**:
  - `EmailBlastIn` + `EmailDraftIn` (`routes/email.py`) now accept `external_emails: List[str]`. `custom_user_ids` was already plural — the frontend just hadn't exposed it.
  - `resolve_segment` parses externals via a strict regex (`[^@\s,;]+@[^@\s,;]+\.[^@\s,;]+`), normalizes/dedupes case-insensitively, drops malformed entries silently, and dedupes the final list against member emails so admins can't double-send. Also fixed an edge case where `segment=custom` with empty `custom_user_ids` would silently blast every active member — now returns 0 members and lets externals through.
  - `Admin.jsx` `EmailBlastAdmin`: single-select `individualId` → multi-select `individualIds` array with badge-style chip UI (each member has a `×` remove button). New external-emails `<textarea>` (newline / comma / semicolon separated) with an inline note explaining opt-out preferences don't apply to external recipients. Both new fields persist in drafts and round-trip on load.
- **Tests**: new `tests/test_iteration90_photo_cache_and_email_multi.py` — **8/8 pass** (ETag emission, 304 short-circuit, 404 on missing files, externals-only preview, members+externals combo, case-insensitive dedupe against member emails, draft round-trip, empty-custom-segment safety). Combined email + photos + members regression suite: **78/78 pass**.

### Iteration 89.4 — Modularization: extract `routes/members_admin.py` (2026-02-25) [P1]
- **`routes/members_admin.py` (new, ~657 lines)**: full extraction of the admin member CRUD + bulk-import surface out of `server.py`:
  - `POST /api/admin/members` — create
  - `POST /api/admin/members/bulk-import` — CSV bulk import (handles renewal_date → +365d, set-password email per row, duplicate detection)
  - `GET /api/admin/members/bulk-import/template` — CSV template download
  - `POST /api/admin/members/{uid}/resend-set-password` — single token resend
  - `POST /api/admin/members/bulk-resend-set-password` — bulk token resend for everyone flagged `pending_set_password=true`
  - `PUT /api/members/{uid}` — admin update (role/tier/expiry guarded to full admins)
  - `DELETE /api/members/{uid}` — hard-delete personal data, soft-delete chat threads, anonymize PayPal txns
  - `PUT /api/members/{uid}/role` `/chapter` `/tier` — focused single-field changes
- **`server.py`: 4,436 → 3,756 lines (-680 lines, ~15% smaller).** Wired via the same `register(api, **deps)` pattern used by other extracted modules; `RESEND_API_KEY` is read via a callable (`resend_api_key_getter`) so future re-key swaps don't require re-registration.
- **Tests**: new `test_iteration89_4_members_admin_module.py` — 5/5 pass (module exports + server.py no longer owns symbols + template endpoint + create/update/role/delete roundtrip + duplicate-email rejection). Full regression suite re-run: **74/74 pass.**

### Iteration 89.3 — Admin override on built-in automated-email campaigns (2026-02-25) [FOLLOW-UP]
- **Backend `routes/automated_emails.py`**: dropped the "Built-in automated emails cannot be deleted" 400. Deleting a built-in now tombstones the id in `deleted_builtin_automated_emails` and the boot-time `seed_builtin_*` functions honor the tombstone so they don't silently resurrect deleted built-ins. The dues-reminders PUT now also persists the `name` field (previously dropped).
- **Frontend `AutomatedEmailsAdmin.jsx`**: delete-bin is now visible for built-ins (with a `window.confirm` explainer noting the tombstone is reversible). The Title input is no longer disabled for built-ins, and the explainer text was rewritten to reflect the new override policy.
- **Test changes**: `test_phase_o.py::test_delete_builtin_forbidden` → `test_delete_builtin_now_allowed_for_admins` (idempotent — restores via direct Mongo write). New `tests/test_iteration89_3_admin_override_builtins.py` covers the full delete-tombstone-restore-reseed loop + the dues-reminder rename + the 404 path. All 3 new tests pass; the broader iter88+iter89 + phase_o suite still **40/40 green**.

### Iteration 89.2 — Admin override on default photo album rename (2026-02-25) [FOLLOW-UP]
- **User feedback**: "Admins should have override authority to change or delete anything on the website" — the previous block on renaming default albums was too conservative.
- **Backend `routes/photos.py` PUT**: removed the `is_default` early-return; renaming a default album now tombstones the old canonical name in `deleted_default_albums` (so the boot-time `seed_default_photo_albums` won't recreate it) and demotes the album to `is_default=False`. Photos cascade-rename as usual.
- **Frontend `Photos.jsx`**: dropped the disabled state on the Title input for default albums. The helper text now reads "Renaming this default album will convert it into a custom album (the original name won't be re-created on the next boot)." so admins know exactly what flip-the-default-bit-off implies.
- **Tests**: replaced `test_default_album_rename_blocked` with `test_default_album_rename_now_allowed_for_admins` — asserts the rename succeeds, the tombstone row exists with the correct `renamed_to` value, and `is_default` is flipped to False. Cleanup fully reverses the mutation via pymongo (`deleted_default_albums.delete_one` + restore `is_default=True`). **All 11/11 iter89 tests pass.**

### Iteration 89.1 — Sub-event RSVP-closed lockdown (2026-02-25) [FOLLOW-UP]
- **Backend**: nothing new — sub-events are regular event documents so the same `rsvps_closed` enforcement on `POST /events/{id}/rsvp`, `PUT /events/{id}/rsvp/guests`, and `POST /events/{id}/payment/confirm` already protects them.
- **`EventDetail.jsx` `SubEventForm`**: added a new `sub-event-rsvps-closed-toggle` checkbox in the inline sub-event edit modal (mirrors the main event editor's amber-bordered toggle). PUT payload now includes `rsvps_closed`.
- **`EventDetail.jsx` `SubEventCard`**: added a small amber `🔒 RSVPs closed` pill (`data-testid=sub-event-rsvps-closed-pill-{id}`) so the lockdown is visible at a glance from the parent event's sub-events panel.
- **Tests**: extended `test_iteration89_album_rename_and_rsvp_lockdown.py` with `test_sub_event_lockdown_is_independent_of_parent` — verifies the sub's `rsvps_closed=true` blocks member self-RSVP (403), doesn't bleed into the parent's flag, and admin `/admin-rsvp` still creates the RSVP. **All 11/11 in iter89 pass.**

### Iteration 89 — Photo album rename + RSVP-closed lockdown (2026-02-25) [FEATURE]
- **Photo album rename** (`routes/photos.py` + `pages/Photos.jsx`):
  - `AlbumUpdateIn` now accepts `name`. PUT validates non-empty, blocks renaming default (`is_default=true`) albums, blocks case-insensitive name collisions across other albums, and cascades the rename to every photo whose `album` field referenced the old name.
  - `EditAlbumDialog` exposes a new Title input (`data-testid=edit-album-name-input`), pre-filled with the current name. The input is disabled with a yellow hint for default albums.
- **RSVP-closed lockdown** (admins-only headcount mode):
  - `models.EventIn` / `EventUpdateIn` gain `rsvps_closed: bool` (default `False`). `event_out` exposes it.
  - `routes/rsvps.py`: `rsvp_event` (POST), `event_payment_confirm` (POST), and `update_rsvp_guests` (PUT) now return **403** with a clear message when `event.rsvps_closed` is true and the caller is not an admin. `admin_rsvp_event` deliberately bypasses the lockdown so admins keep full control.
  - `pages/Admin.jsx`: new orange `event-rsvps-closed-toggle` renders below the existing cancelled toggle (only when the event isn't cancelled) with an explainer about the lockdown.
  - `pages/EventDetail.jsx`: computes `rsvpsLocked = event.cancelled || (event.rsvps_closed && !isAdmin)` and gates every member-facing button on it. Renders an amber `event-rsvps-closed-notice` plus a disabled `rsvp-btn-closed` for non-admin members; admins retain `AdminRsvpForMemberDialog` and `AdminManageRsvpsDialog`.
- **Tests**: new `tests/test_iteration89_album_rename_and_rsvp_lockdown.py` — **10/10 pass** (rename happy-path + empty-name + case-insensitive clash + default-album block + category-combo; rsvps_closed surfaces on event_out + member POST/RSVP-guests blocked + admin-rsvp still works + re-open restores access). Existing RSVP/album regressions still **36/36 green**.
- **Verification** (`testing_agent_v3_fork iteration_89.json` — `retest_needed: false`, 0 action items): both flows confirmed end-to-end through the deployed preview UI as admin AND member (Riley Chen).

### Iteration 88 — Modularization: extract automated_emails out of server.py (2026-02-25)
- **`routes/automated_emails.py` (new, ~830 lines)**: extracted the entire automated-email subsystem out of `server.py`:
  - Admin CRUD + preview + run-now endpoints (`GET/POST/PUT/DELETE /api/automated-emails`, `/merge-tags`, `/dues-reminder-defaults`, `/{eid}/preview`, `/{eid}/run-now`).
  - Broadcast renderer with all 7 merge tags (`{{member_name}}`, `{{upcoming_events}}`, `{{new_photos}}`, `{{new_documents}}`, `{{new_members}}`, `{{my_rsvps}}`, `{{pending_hours}}`, `{{birthday_greeting}}`).
  - Dues-reminder cadence (30d/15d/5d/+1d) with per-stage editable templates + the admin dues-summary digest (`_send_admin_dues_summary`).
  - Built-in seeds (`seed_builtin_automated_emails`, `seed_builtin_dues_reminders`) and the 5-minute background runner (`_automated_email_loop`).
  - Module-level state (`db`, `RESEND_API_KEY`, `resend_sdk`, `now_utc`, …) bound by `register(...)` so tests can monkey-patch `routes.automated_emails.db = fake_db` cleanly.
- **`server.py`**: shrank from **5,176 → 4,435 lines (-741 lines, ~14%)**. Replaced the deleted block with a thin pointer comment + startup-side hooks (`asyncio.create_task(routes_automated_emails.register.automated_email_loop())` etc).
- **Tests**:
  - `test_iteration88_automated_emails_module.py` — 5/5 pass (helper export shape, server.py no longer owns extracted symbols, endpoints still served, preview renders both kinds, unauth → 401).
  - Updated `test_iteration53_dues_admin_summary.py` to mock `routes.automated_emails` instead of `server` (helpers now live there).
  - Updated `test_iteration47_email_preferences.py` static inspection to scan `routes/automated_emails.py` + `routes/email.py` for the dues + blast Mongo query clauses.
  - Email/regression suite: **46 passed, 1 skipped** (test_iteration46/47/53/64_extra/65/84/88 + iteration88).

### Iteration 87 — Personnel Data Brief + Detailed variant + RSVP date toggle (2026-02-24) [FEATURE]
- **Renaming**: "Personnel Brief" → "Personnel Data Brief" in tab label, PDF metadata title, and filename slug.
- **Two side-by-side downloads** (`Reports.jsx` `BriefReport`):
  - `brief-pdf-one-pager-btn` (filled primary) — calls `/reports/personnel-brief/{id}/pdf` → one-page ORB landscape.
  - `brief-pdf-detailed-btn` (outline) — calls `/reports/personnel-brief/{id}/pdf?detailed=true` → one-pager **+** multi-page §III-§XI full-history attachments (civilian education, languages, dues, donations, community service, awards, OTY, event attendance, assignments). Both buttons enabled only after picking a member; downloads use the correct slug (`personnel-data-brief` vs `personnel-data-brief-detailed`).
  - In-dialog preview also exposes both download options (`brief-dialog-pdf-one-btn`, `brief-dialog-pdf-detailed-btn`).
- **Backend `routes/reports.py`**: `/reports/personnel-brief/{id}/pdf` now accepts `?detailed=true`. When true, builder appends a `PageBreak()` and 9 detail-section tables. Footer label flips between "GENERATED yyyy-mm-dd" and "DETAILED ATTACHMENTS FOLLOW".
- **RSVP date-context toggle** (`RsvpsReport` + backend):
  - Frontend pill toggle in the Filters card: "📅 Filter by: RSVP date · Event date".
  - Backend `report_rsvps()` + `report_rsvps_summary()` accept `date_field=rsvped_at|event_start_at`. `rsvped_at` (default) filters on `rsvps.created_at`; `event_start_at` first scopes event_ids by start_at then constrains the rsvp query. `by_period` bucket key follows the same toggle.
  - Confirmed deltas (preview env): year=2026 rsvped_at → 7, event_start_at → 1; year=2027 event_start_at → 6.
- **Verification (testing_agent_v3_fork iteration_87.json — `retest_needed: false`)**: 100% backend + frontend pass. Both PDFs validated by pypdf (page count + section header text). Both buttons render side-by-side at same y-position. RSVPs toggle reissues request with proper `date_field` param. Zero issues, zero action items.

### Iteration 86 — RSVP filter year/quarter bug fix (2026-02-24) [BUG FIX]
- **Reported bug**: "Admin RSVPs filter is not registering correctly. year=2026 shows only one person; quarter shows nothing; all-years shows everyone."
- **Root cause**: iter81 implementation applied the period filter against `events.start_at` — so RSVPs to events scheduled outside the picked year/quarter were dropped. The user's 7 RSVPs were all placed in Jun-2026 but the events themselves are scheduled in 2027, so year=2026 dropped all but the lone event-in-2026 row.
- **Fix**: `report_rsvps()` in `routes/reports.py` now filters by `rsvps.created_at` (matches Hours/Donations activity-date semantic). `report_rsvps_summary()` `by_period` bucket key also switched from `event_start_at[:7]` to `rsvped_at[:7]` so the bucket dates align with the rows shown in "Individual entries". Doc-string updated.
- **Verification (testing_agent_v3_fork iteration_86.json — `retest_needed: false`)**:
  - year=2026 → 7 rows (was 1 before fix)
  - year=2026 + Q2 → 7 rows (was 0 before fix)
  - year=2026 + Q1 → 0 rows (correctly empty)
  - by-period summary buckets correctly by rsvped_at month
  - Playwright UI confirms RSVPED column dates match the selected window
  - iter81 regression suite still passes (8/8)
  - 0 action items, 0 critical/minor issues

### Iteration 85 — Personnel Brief: titles fixed + true one-pager (2026-02-24) [BUG FIX]
- **Reported bug**: "On the personnel brief, the titles of the sections are missing on the first page. I would like to only see a one-pager."
- **Root cause**: Section bars were built with `Paragraph(backColor=AOP_NAVY, …)`. When wrapped inside the 3-column sub-table cells, ReportLab was rendering the navy strip but the title text was getting clipped/lost in some layout configurations.
- **Fix #1 (titles)**: Replaced the Paragraph-with-backColor approach with a dedicated `orb_section_bar(label_html)` helper that builds a single-cell Table with `BACKGROUND=AOP_NAVY` + white text inside. This is the standard ReportLab idiom for filled section bars and renders the title reliably regardless of nesting context. All 8 page-1 section bars now use this helper.
- **Fix #2 (one-pager)**: Removed everything from the former `PageBreak()` through the detail-attachment block (~118 lines of `data_table()` + Section III-XI full-history tables). The Personnel Brief is now strictly a one-pager. The 3-column ORB grid carries top-N most-recent rows with "(N TOTAL)" / "(TOP X OF Y)" annotations so admins still see the cap.
- Footer wording adjusted from "PAGE 1 OF DETAIL FOLLOWS" → "GENERATED {date}" to match the new single-page reality.
- **Verification (testing_agent_v3_fork iteration_85.json)**: Both PDFs (admin + member) return HTTP 200, **page_count == 1**, and all 8 SECTION I-VIII titles present in extracted text. Frontend on-screen preview still renders correctly. No regressions. `retest_needed: false`.

### Iteration 84 — rsvps.py split + documents module extracted (2026-02-24)
- **`routes/rsvps.py` modularization**: extracted check-in scan/lookup → `routes/checkin.py` (~97 lines) and bulk-CSV import → `routes/rsvps_csv.py` (~242 lines). The parent `rsvps.py` retains the shared QR token / email-ticket / cancellation-guard helpers and exposes them via attribute injection on the `register` fn so sub-modules can call into the shared logic. **`rsvps.py`: 955 → 648 lines (~32% reduction)**.
- **`server.py` modularization (Documents)**: extracted `/api/documents*` + `/api/document-folders*` routes (single + bulk upload, folder CRUD, list with category/folder filter, soft-delete) into `routes/documents.py` (~243 lines). **`server.py`: 5,345 → 5,176 lines**.
- **Tests**: `test_iteration84_modularization_smoke.py` — 5/5 pass (checkin lookup/scan reachable, CSV template, documents+folders list, folder CRUD roundtrip). Full regression iter74-84 → **44/44 green**.

### Iteration 83 — Inline Approve/Reject on Zeffy event-ticket inbox tab (2026-02-24)
- **Frontend `AdminDashboard.jsx`**: Each pending Zeffy ticket row in the inbox now has inline **Approve** (emerald) and **Reject** (red outline) buttons + a smaller "Open in Reports →" secondary link. Approve calls `PUT /api/transactions/{id}/approve-event-ticket` (creates RSVP + emails QR ticket); Reject calls `DELETE /api/transactions/{id}` (removes the pending row). Both show a `window.confirm` with the submitter + event + amount + Zeffy conf # so the admin sees the full context before acting.
- **Tests**: `test_iteration83_inbox_inline_buttons.py` — 2/2 pass (Reject removes from inbox + underlying DB; Approve endpoint stays wired for missing tx).
- Full regression iter74-83 → **39/39 green**.

### Iteration 82 — Quick family check-in + umbrella payment hide + Photos modularization (2026-02-24)
- **Quick "Family" check-in mode (Task 1)**: `EventDetail.jsx` CheckInDialog gains a 3rd tab "Quick · Family". Shows every member RSVP grouped with their guests; tap the family header to multi-select member + all their guests (the common "family arriving together" pattern) or check individual rows. Submit fires sequential `/check-in` POSTs and reports `Checked in N · M failed` via toast.
- **Hide payment-mode selector on umbrella parents (Task 2)**: `Admin.jsx` event editor now detects umbrellas via `subDrafts.length > 0 || existingChildrenCount > 0` (loads `/events/{id}/sub-events` once on mount for existing events) and replaces the Free/Zeffy/External card with a dashed-border note "Payment / Tickets · configured per sub-event". Eliminates the dead-config footgun.
- **Photos module modularization (Task 3)**: Extracted `/api/photos*` + `/api/photos/albums*` routes from `server.py` to `routes/photos.py` (~310 lines moved). Seed helpers (`DEFAULT_PHOTO_ALBUMS`, `seed_default_photo_albums`, `auto_categorize_album`, `PHOTO_ALBUM_CATEGORIES`) stay in `server.py` since they run at startup before route registration. `server.py`: **5,643 → 5,345 lines** (5.3% reduction). Routes registered via `routes_photos.register(...)` with explicit dependency injection.
- **Tests**: `test_iteration82_photos_module_and_quick_checkin.py` — 3/3 pass (photos endpoints smoke + album round-trip + quick-family batched check-in). Full regression iter74-82 → **37/37 green**.

### Iteration 81 — Reports RSVPs parity + cancellation emails + admin inbox tickets (2026-02-24)
- **Reports → RSVPs filter parity** (Task A): `RsvpsReport` in `pages/Reports.jsx` now matches Hours/Donations — Year (incl. "All Years"), Period (Q1-Q4, Jan-Dec), Parent event, Sub-event, Ticket type filters + 4 view pills (Individual entries / By member / By chapter / By period). Backend `/api/reports/rsvps` accepts `year, quarter, month, ticket_type, parent_event_id, event_id`; new `/api/reports/rsvps/summary?group_by=member|chapter|period` returns totals + buckets.
- **Calendar "This month at a glance" cancelled label** (Task B): cancelled events now render with a red border, struck-through title, and a `● Cancelled` pill (`data-testid="cal-event-cancelled-{id}"`).
- **Cancellation email fan-out** (Task B): `routes/events.py` PUT cascade now schedules a Resend email to every RSVP'd member + guests-with-email via `_send_cancellation_emails()`. Fire-and-forget asyncio task — never blocks the API response. Skips silently when `RESEND_API_KEY` isn't configured. De-dups recipients across umbrella + child events (one email per member).
- **Per-sub-event check-in** (Task C): already supported architecturally — each sub-event renders its own `<CheckInPanel eventId={subId}>` so check-ins are scoped per event. Confirmed by iter79's test coverage; no code changes needed.
- **Zeffy payment visibility** (Task D): `/api/admin/stats` inbox now exposes `inbox.pending_event_tickets[]` (newest 20). `AdminDashboard.jsx` InboxPanel surfaces them as a "Zeffy event tickets" tab with the submitter, event, amount, Zeffy confirmation #, and a "Review →" link to `/reports?tab=event_tickets`.
- **Tests**: `test_iteration81_reports_cancel_inbox.py` — 8/8 pass. Full regression iter74-81 → **34/34 green**.

### Iteration 80 — Sub-events accept free / Zeffy-paid / external-link modes (2026-02-24)
- **Frontend `Admin.jsx`**: The sub-event draft form (used when creating a new parent + sub-events together) now exposes a compact 3-option RSVP/payment mode selector (Free RSVP / Paid via Zeffy / External link), mirroring the parent's selector. Selecting Zeffy reveals payment URL + amount inputs; selecting External reveals URL + button-label inputs.
- **Save path**: `is_paid`, `payment_url`, `payment_amount`, `external_url`, `external_button_label` are now included on every sub-event POST so the umbrella's child events can independently be free, paid (Zeffy), or external-link-driven. Editing an existing sub-event via the standard event-edit dialog already exposed these — only the bulk-draft form lacked them.
- **Backend behaviour** (already correct, now exercised by tests): paid sub-events route members through the existing `/events/{id}/payment/confirm` Zeffy flow (free RSVP returns 402 with the routing hint); external sub-events are surfaced as a "Get tickets" button on the frontend (backend RSVP still permitted as a UI escape hatch).
- **Tests**: `test_iteration80_subevent_modes.py` — 4/4 pass (mode persistence + free RSVP / paid 402 routing / external no-block behaviour).

### Iteration 79 — Guest check-in dropdown with search + manual fallback (2026-02-24)
- **Frontend `EventDetail.jsx`**: The admin Check-In dialog's "Guest" tab now mirrors the Member tab — flattens every RSVP'd guest across all member RSVPs into a searchable list (search by guest name, email, or host member name). Picking a guest pre-fills their RSVP'd ticket type and links the check-in to their host member via `host_user_id` so reports group them correctly.
- **Already-checked-in guests are hidden** (matched by `(host_user_id, normalized_name)` against the existing checkins list, same shape used by the backend `/check-in-roster` endpoint).
- **Manual fallback**: "+ Guest not listed? Type their name manually" toggles a free-text input for walk-ins (no host linkage). "← Back to RSVP guest list" returns to the dropdown.
- **Reset on close**: Closing the dialog resets all form state so next open is clean.
- **Tests**: `test_iteration79_guest_checkin_dropdown.py` — 3/3 pass (guest+host linkage, duplicate-guest 400 guard, walk-in escape hatch).

### Iteration 78 — Pending Password Setup badge stays permanent until member resets (2026-02-24)
- **Bug fix (root cause)**: `routes/auth.py` no longer auto-clears `pending_set_password` on a successful login. Bulk-imported members can sign in with an admin-set temporary password without ever completing the `/set-password` welcome flow — the old behaviour silently flipped the flag off in that case.
- **Proper clears (member-driven)**: `/auth/reset-password` and `/auth/change-password` now clear `pending_set_password` (in addition to `/auth/set-password`, which already did). The flag only clears when the member themselves completes a password action.
- **Admin override unchanged**: `PUT /api/members/{id}` with `new_password` still clears the flag (intentional — admin has explicitly verified onboarding).
- **Boot migration**: New `reconcile_pending_set_password()` runs at startup. It re-flags any member whose `pending_set_password` is currently false BUT who had a `password_set_tokens` row issued AND never consumed one via `/auth/set-password` (only invalidated-on-resend rows present). Idempotent — re-runs are no-ops once the data is consistent.
- **First production-style run**: migration re-flagged 2 incorrectly-cleared members on the first restart, then "all candidates already correctly flagged" thereafter.
- **Tests**: `test_iteration78_pending_setpw.py` — 5/5 pass (login no-clear regression, reset/change/set-password clears, migration re-flag).

### Iteration 126 — RSVP ticket recipients contract + dark-mode blue text fix (2026-07-13)
- **RSVP ticket delivery locked in**: verified `send_rsvp_ticket_email` (which every RSVP creation path funnels through — member self-RSVP, admin-driven RSVP, guest additions, paid-after-approval) sends TO **both** the member AND `info@alphaomegaphi.org`. Backend log line proves live delivery: `"RSVP ticket email sent to <member> (+ info@alphaomegaphi.org) for <event>"`. Configurable via `EVENTS_INBOX_EMAIL` env var (defaults to `info@alphaomegaphi.org`). Case-insensitive dedupe prevents double-sending when the member IS the events inbox.
- **3 new tests** in `test_iteration126_rsvp_ticket_recipients.py`: recipient contract check, dedupe when member email == events inbox, env-var override honored.
- **Note**: In the preview environment Brevo returns HTTP 401 because the container's egress IP isn't in the Brevo authorized-IPs list — this is a Brevo-account allowlist configuration and doesn't affect the code. Production has its own IP allowlist to keep updated.
- **Dark-mode navy text → white**: expanded `index.css` dark-compat layer with rules matching every serialized form React emits for `style={{ color: NAVY }}` (`rgb(10, 36, 99)` and `#0A2463` / `#0a2463`) plus the arbitrary `text-[#0A2463]` and `text-blue-500..900` Tailwind classes. Fixes hundreds of headlines/labels across Home, Chat, Gear, Donate, Meet, Calendar, and Photos without touching any component. Verified via screenshot: Chat title, Gear item names, Calendar day numbers all now render white in dark mode; light mode unchanged.

### Iteration 125 — Dark-mode contrast fixes across Chat, Profile, Hours, Awards (2026-07-11)
- **New dark-mode compatibility layer** in `index.css` — remaps the most common light-first Tailwind classes (`bg-white`, `bg-slate-*`, `text-slate-*`, `border-slate-*`, `hover:bg-slate-*`) to theme-aware equivalents (`bg-card`, `bg-muted`, `text-muted-foreground`, `text-foreground`, `border-border`) when `.dark` is active. Fixes hundreds of components at once without a per-file sweep.
- **Colored status badges** (emerald/amber/red/blue for "Approved"/"Pending"/"Rejected"/info) now have saturated dark-mode HSL variants so they remain visible on dark cards.
- **Trophy tiles in Awards**: added `award-icon-tile` class + CSS override that swaps the near-invisible `${color}33` inline background for `hsl(var(--muted))` in dark mode and brightens the icon via `filter: brightness(1.4)` so trophy pictures stay legible.
- **"Approved" pill in Volunteer Hours**: fixed the hardcoded `text-[hsl(34_8%_16%)]` (near-black amber) → `text-foreground` so it renders on any theme. Extended with a global CSS override for the arbitrary HSL literal so every other component using the same legacy pattern (`AdminDashboard`, `EventDetail`) inherits the fix.
- **Verified all 4 modes** (light, dark, mono, system) with screenshots. Light theme unchanged; dark theme now has clearly visible video/settings buttons in Chat, all profile boxes, the Approved pill, and every trophy tile.

### Iteration 124 — Theme switcher: light / dark / black-and-white / system (2026-07-11)
- **New `ThemeProvider`** in `lib/theme.jsx` — React context that persists to `localStorage["aop.theme"]`, resolves `system` to the OS preference via `prefers-color-scheme`, and toggles `.dark` / `.mono` classes on `<html>`.
- **New `.mono` theme** in `index.css` — pure grayscale HSL variables + a global `filter: grayscale(100%)` on `.mono` so every element (Tailwind hardcoded colors, brand gradients, uploaded photos) renders truly monochrome. High-contrast, a11y-friendly.
- **New `ThemePicker` component** with two modes: `menu-item` (embedded in the Navbar user menu with an "APPEARANCE" section) and `standalone` (pill button shown for logged-out visitors on the marketing pages so guests can flip themes too).
- Wired into Navbar user menu + as a standalone pill next to the "Member login" button for anonymous visitors.
- **Provider hierarchy**: `ThemeProvider > AuthProvider > SiteSettingsProvider > BrowserRouter`, so theme state is available before any route mounts.

### Iteration 123 — Admin-configurable per-role hours behavior (2026-07-11)
- **Backend** (`routes/hours.py`):
  - New `db.app_settings.hours_role_config` doc — shape `{ roles: { <role>: { can_manage_others, default_mode } } }`.
  - New endpoints: `GET /api/hours/role-config` (any authenticated user — used by the frontend to decide UI) and `PUT /api/hours/role-config` (Full Access only). Rejects invalid `default_mode` values and unknown-shaped payloads with 400.
  - `_can_manage_hours_for_others()` is now async and reads the merged config on every check — a runtime flip immediately affects `POST /hours/admin`, `/admin/bulk`, `/admin/csv`, `PUT /review`, and `PUT /hours/{id}`.
  - Built-in defaults preserved for the 4 known roles; unknown roles conservatively default to `{ can_manage_others: false, default_mode: "for_myself" }`.
- **Frontend**:
  - New `HoursRoleConfigAdmin` component in Admin → Pages tab — table with a toggle per role (manage-others) and a mode dropdown, plus an "Add new admin role key" input so future sub-roles need zero code changes.
  - `Hours.jsx` now fetches the config once on mount and passes it to `LogHoursDialog`; `canManageOthers` and the default `logForMyself` state are both derived from the config with graceful fallback to the payload's `defaults` block. Removes the hardcoded `["full", "operations_manager"]` gate.
- **Tests**: 6 new tests in `test_iteration123_hours_role_config.py` (schema shape, admin-only writes, runtime permission flip round-trip on Governor Manager, adding an unknown role, invalid input rejection, public read). 37/37 across iter116–123.

### Iteration 122 — Hours: sub-admin lock-down + review reserved for Full Access + Ops Manager (2026-07-10)
- **Backend** (`routes/hours.py`): all "act on someone else" hours endpoints — `POST /hours/admin`, `POST /hours/admin/bulk`, `POST /hours/admin/csv`, `PUT /hours/{id}/review`, `PUT /hours/{id}` — now hard-restricted to Full Access + Operations Manager admins. Governor Manager and Membership Manager can only log for themselves via `POST /hours` (returns `pending`, routed to Full/Ops Manager for approval).
- **Frontend** (`Hours.jsx`):
  - Governor Manager & Membership Manager no longer see the Review Queue tab or the CSV Import button.
  - The Log Hours dialog no longer shows the "Log for others / Log for myself" toggle for these sub-roles — they see the same personal-entry form every regular member sees, ending in "Submit for approval".
  - Full Access + Operations Manager admins retain the toggle and can still switch between "Log for others" (auto-approved) and "Log for myself" (queued for another Full Access admin).
- **Tests**: 7 new tests in `test_iteration122_hours_subadmin_lockdown.py` (lock-down on `admin`, `admin/bulk`, `admin/csv`, `review`, plus positive tests that both sub-roles CAN still log their own hours and Full Access can still review). Iter121 test updated to lock in the *new* restrictive rule. 31/31 regression across iter116–122.

### Iteration 121 — Governor Manager & Membership Manager can log their own hours (2026-07-10)
- **Bug**: Any admin user opening the "Log hours" dialog on `/hours` was force-routed into admin-mode which (a) required picking another member before submitting, and (b) POSTed to `/hours/admin` (requires the `hours` admin tab). Governor Manager technically had the tab but couldn't log for themselves; Membership Manager didn't have the tab and got 403 either way.
- **Fix**: `Hours.jsx` `LogHoursDialog` gains a "Log for others / Log for myself" toggle for admin users. "Log for myself" hides the member picker, restores the full required-field set, and POSTs to `/hours` (member endpoint that uses `get_current_user`). The default is smart: Full admins + Governor Managers land on "Log for others" (their normal flow); Membership Managers and any sub-role without `hours` tab land on "Log for myself".
- **Tests**: 4 new tests in `test_iteration121_admin_own_hours.py` locking in the behavior end-to-end (Governor + MM own-hours, MM 403 on admin endpoint, Governor still logs for chapter peers). 24/24 regression across iter116–121 green.

### Iteration 120 — Automatic award grants + Service Ribbon year-scoping fix (2026-07-08)
- **Year-scoping fix (bug)**: `routes/awards.py` Service Ribbon eligibility now strictly buckets by `anniversary.year == queried_year`. Previously, a 5-year milestone earned in 2025 would leak into the 2026 view during the pre-anniversary window each new year. Fixed.
- **New module `routes/awards_auto.py`**: shared helpers + daily background loop for automatic award grants. Every grant is tagged `auto_granted=True`, `granted_by="system:auto"`, and `auto_grant_kind ∈ {alpha_omega_phi_ribbon, service_ribbon, community_service_ribbon}`.
  - **Alpha Omega Phi Ribbon** — auto-granted on join. Hooked into every member-creation path: `POST /admin/members`, bulk-import (`POST /admin/members/bulk-import`), public application approval (`routes/applications.py`), and public self-registration (`routes/auth.py`). Idempotent per user.
  - **Service Ribbon** — daily sweep. Fires only on the actual MM/DD anniversary at milestones (1yr, then every 5yrs). Uses the reactivation clock (`reactivated_at` → latest `status_history` "active" entry → `join_date` → `created_at`), so a member who went inactive and paid dues starts counting from their renewal date. Dedupes on `(user, award, reason)`.
  - **Community Service Ribbon (annual 100+ hrs)** — sweep is a no-op on every day except Dec 31, when it grants every active member with ≥100 approved hours in that calendar year. Dedupes on `(user, year)`.
- **Admin surfaces** (`/api/admin/auto-grants` + `/api/admin/auto-grants/run-now`):
  - `Admin.jsx` Awards tab gains an "**Recent automatic grants**" panel with a 7/30/90/365-day filter, per-kind chip filters with live counts, a table of every fired grant with reason, and a "Run sweep now" button (useful right after deploy or on Dec 31 morning).
  - Every ribbon in the member card now shows an **AUTO** pill next to the award name when it was auto-granted.
- **Tests**: 5 new tests in `test_iteration120_auto_award_grants.py` covering join grant, year-scoping, reactivation-clock anniversary logic, Dec 31 annual sweep + dedupe, and admin-only auth on the new endpoints. Full regression 23/23 across iter114–120.

### Iteration 119 — Member-side SMS opt-in/out preferences (2026-07-07)
- **Backend**: New `GET/PUT /api/me/sms-preferences` symmetric to `/me/email-preferences`. Persists `sms_opt_out` (master + timestamp) and `sms_prefs.dues_reminders` (granular per-category). Re-enabling any sub-category auto-clears the master opt-out — same ergonomics as the email side.
- **Dues-reminder SMS honors both flags**: `routes/automated_emails.py::_send_dues_reminders` projects `sms_opt_out` + `sms_prefs`, and skips the SMS companion when either the master flag OR `sms_prefs.dues_reminders` is off.
- **Frontend**: New `SmsPreferences` panel in `Profile.jsx` under the Notifications tab. Copy calls out standard message/data rates and the STOP opt-out. Shows a "no phone number on file" banner when phone is empty (toggles disabled). Auto-clears the master opt-out when re-enabling a sub-category, matching backend semantics.
- **Tests**: 3 new tests in `test_iteration119_member_sms_prefs.py` covering the toggle flow, auth gate, and the dues-reminder fan-out honoring per-category opt-out. All green (19/19 iter101/116/117/118/119).

### Iteration 118 — SMS kill-switch + Dues-reminder SMS companion + Member's Ribbon per-category rows (2026-07-07)
- **Fixed backend crash**: Removed orphaned dead code left in `routes/awards.py` (lines 695–704) that prevented the backend from starting after the previous session.
- **Member's Ribbon eligibility (backend)**: `routes/awards.py` now returns `aop_hours`, `total_hours`, `recruits`, `donated_amount`, `checkins`, `top_in[]`, and `category_count` for **every** candidate member — no more "no context" rows. A member is a candidate if they broke into top-5 in ANY category.
- **Member's Ribbon eligibility (frontend)**: `Admin.jsx` Awards Eligibility panel now renders all 5 categories as their own row per member (with dot marker + highlight for top-5 placements), exactly as user requested. `EligibilityCard.format` extended to receive the whole row so custom cells can render.
- **Global SMS kill-switch**: New `GET/PUT /api/admin/sms-config` endpoints backed by `db.app_settings.sms_config`. `send_sms()` short-circuits BEFORE hitting Brevo/Twilio when `enabled: False`. New `SmsSettingsAdmin.jsx` panel in Admin → Pages tab shows current status, provider, and last-changed metadata with a one-click toggle + confirm.
- **Dues-reminder SMS companion**: `_send_dues_reminders` in `routes/automated_emails.py` now also fires an SMS via the same Brevo path immediately after the email is queued, for members with a phone number and no `sms_opt_out`. Copy stays under 320 chars per stage (30d / 15d / 5d / grace) with STOP language. Respects the global kill-switch.
- **Tests**: 5 new tests in `test_iteration118_sms_killswitch_and_ribbon.py` (all pass). Regression across iter101/114/116/117 (14 tests) — all green.

### Iteration 77 — Per-event ticket type filtering on all guest selectors (2026-02-24)
- **Frontend `EventDetail.jsx`**: The member-side `GuestManager`, the admin-side `AdminRsvpForMemberDialog` member-ticket select, and its per-guest-ticket select all now read `event.enabled_ticket_types` and render only the options actually enabled for that event. Legacy events with an empty `enabled_ticket_types` fall back to the canonical four (VIP / All Access / General / Guest) so behaviour is unchanged for un-migrated rows.
- Member-side member-ticket picker already followed this pattern (`MemberTicketPicker`) — admin-side selectors now match.
- Added small `ticketTypeLabel()` helper + `TICKET_TYPE_LABELS` map at the top of `EventDetail.jsx` to keep human-readable labels consistent.
- "guest" is automatically filtered out of the member-ticket select (members aren't guests) but kept available for guest rows.

### Iteration 76 — Admin delete default albums + per-guest ticket type on admin RSVP (2026-02-24)
- **Backend**: `DELETE /api/photos/albums/{id}` now lets admins delete *any* album, including default canonical ones. A tombstone is written to a new `deleted_default_albums` collection and the boot-time seeder skips tombstoned names so deletion sticks across restarts. Non-admin members still get 403 on default albums.
- **Frontend**: `Photos.jsx` AlbumCard — admins now see the delete (trash) button on default albums too; member creators still only see it on their own custom albums. Confirm dialog includes an extra warning when targeting a default album.
- **Frontend**: `EventDetail.jsx` admin RSVP-for-member dialog now exposes a per-guest ticket-type Select (VIP / All Access / General / Guest) when the event has `allows_ticket_types=true`, matching the member-side guest manager. Backend already accepted the field; data flows end-to-end.
- **Tests**: `test_iteration76_album_delete_and_guest_tickets.py` — 2/2 pass. iter74/75 regression green (14/14 total).

### Iteration 75 — Cascade cancellation of sub-events (2026-02-24)
- **Behaviour**: When an admin cancels a parent (umbrella) event via PUT `/api/events/{id}`, every sub-event (`parent_event_id == id`) is also marked `cancelled=true` and tagged `cancelled_via_parent=true`. The cancellation note propagates to children that didn't have their own.
- **Un-cancel cascade**: Un-cancelling the parent only reverts children that still carry `cancelled_via_parent=true`; sub-events the admin had cancelled independently stay cancelled.
- **Defense-in-depth**: The RSVP helper `_ensure_not_cancelled` in `routes/rsvps.py` also rejects RSVPs / payment / guest edits whenever the parent event is cancelled, even if a particular sub-event somehow has `cancelled=false` (e.g. seeded after parent cancel, or admin manually un-cancelled a child while parent stays cancelled).
- **Direct toggle clears cascade flag**: any direct PUT on an event clears `cancelled_via_parent` so subsequent parent-uncancel cascades don't override manual decisions.
- **Frontend**: `EventDetail.jsx` banner reads "The parent event has been cancelled." when `cancelled_via_parent` is true, otherwise the standard "This event has been cancelled."
- **Tests**: `/app/backend/tests/test_iteration75_cancel_cascade.py` — 4/4 new pass + iter74 (12 cases) regression green.

### Phase BL — Iteration 74: Admin un-RSVP + remove-guest (2026-02-20)
- Backend: `DELETE /api/events/{event_id}/admin/rsvp/{rsvp_id}` and `DELETE /api/events/{event_id}/admin/guest/{guest_id}` in `routes/rsvps.py`. Idempotent (un-RSVP returns 200 with `was_present=false` if missing).
- Frontend: `AdminManageRsvpsDialog.jsx` wired into `EventDetail.jsx` with searchable RSVP list, per-row remove + per-guest remove, browser-confirm, toast + counter refresh on success.
- Tests: 8/8 backend pytest pass; 41/41 RSVP regression green (`test_iteration74_admin_unrsvp.py`).

### Phase BL — Iteration 73: RSVP ticket fix, OTY chapter, ORB-style Personnel Brief (2026-02-15)

**User requests addressed (4):**
A. **Bug** — Admin → Reports → RSVPs showed blank `ticket_type` when no check-in existed yet (only checkin's ticket_type was sourced). Fix: fall back to `rsvp.ticket_type` then 'general' (routes/reports.py L125).
B. **Bug** — Personnel Brief "Of The Year" rows had blank chapter when the OTY doc had no denormalized chapter_name. Fix: 4-step waterfall — denorm name → lookup by chapter_id → walk `users.assignment_history` for the OTY year (new `_chapter_for_year` helper) → fall back to current chapter.
C. **Enhancement** — Admins can now optionally tag a chapter on member-category OTY awards. Backend PUT/POST relaxed (chapter_id no longer rejected). Awards.jsx exposes a "Chapter context (optional)" Select with placeholder "Auto-resolve from assignment history" (`oty-member-chapter-select`).
D. **Enhancement** — Personnel Brief completely rebuilt to look like an Army Officer Record Brief.
   - **PDF:** landscape letter. Page 1 = ORB-style identity header (photo + name in ALL CAPS + right-side 7-field meta grid) + a 3-column ORB grid (Personal Data / Awards & OTY / Assignment-Stats-Events) using new helpers (`orb_kvp`, `orb_list`, `_column`). Pages 2+ = detail tables for SECTION III–XI in ALL CAPS.
   - **On-screen preview:** matching ORB header + new `OrbSummary` component rendering 3-column tile grid (`brief-orb-summary`, `brief-orb-meta`, `orb-oty-tile`) followed by "▼ Detailed Record (Attachments)" divider and the existing detailed sections renumbered to Roman numerals (`brief-section-I` through `brief-section-XI`).

**Verification (iteration 73):** 28/28 active tests pass across iter69–72 regression + iter73 frontend/backend tests. Testing agent verified all 4 user requests end-to-end. PDF text-extraction confirms landscape size + ALL CAPS section headers + section order + dual-page rendering.


### Phase BL — Iteration 72: "Of The Year" on Personnel Brief + Admin Member Card (2026-02-15)

**User request:** "On the personnel brief, add the last 7 'Of The Year' Awards as a section after the Awards section. Also, show every 'Of The Year' award that the member won on the member card in the admin → members section."

**Backend:**
- `GET /api/of-the-year` now accepts optional `user_id` query param → returns just that user's wins (sorted year DESC).
- `personnel_brief_data` (routes/reports.py) returns three new keys: `of_the_year` (full list), `of_the_year_recent` (capped at 7), `of_the_year_count` (int).
- PDF builder renders a new `§9  Of The Year Honors` section between Awards and Events with a 4-column table (Year, Category, Chapter, Note). When a member has >7 wins, the header reads "last 7 of N". Subsequent sections renumbered: §10 Events, §11 Assignment History.
- Defensive chapter-name enrichment: legacy OTY rows missing the denormalized `chapter_name` are looked up against `db.chapters` so the PDF/table never shows a bare "—".

**Frontend:**
- `Admin.jsx` `MemberCardDialog` — loads `/of-the-year?user_id={id}` on dialog open and renders a new "OF THE YEAR HONORS (N)" section below the Ribbons & Achievements section. Each win shown with year + category label + chapter/note. Empty state has `data-testid='member-card-{id}-oty-empty'`. Wins list at `data-testid='member-card-{id}-oty'` with per-row `data-testid='oty-win-{award_id}'`.
- `Reports.jsx` `BriefBody` — new `data-testid='brief-section-9'` titled "Of The Year Honors" rendering the same data as a 4-column table in the JSON brief preview. Existing §9/§10 sections shifted to §10/§11.

**Verification (iteration 72):**
- 7/7 new pytest cases pass + 23/23 regression (iter69/70/71) still pass.
- Backend test file `test_iteration72_of_the_year_brief.py` is self-seeding via an autouse module fixture (creates Maya's two canonical wins on entry, cleans up on teardown — idempotent, dataset-state preserved).
- PDF text-extraction asserts §9 → §10 → §11 ordering and presence of "Of The Year" / "Member of the Year" / "Top Community Service Member".


### Phase BL — Iteration 71: Bulk "add anniversary fee" + outstanding-balance filter pill (2026-02-15)

**User choices:** 1c (manual row-selection), 2a (one shared label+amount), 3a (skip URL during bulk); filter as a pill next to search.

**Backend:**
- New endpoint `POST /api/admin/members/balance/bulk-add-line` in `/app/backend/routes/balances.py`. Body `{user_ids[], label, amount}`. Idempotent: case-insensitive label match against existing UNPAID lines per member skips dupes. Returns `{created_count, skipped_count, error_count, created_user_ids, skipped_user_ids, errors, label, amount}`.
- `public_user` serializer already surfaces `outstanding_balance_total` on `/api/members` rows (added iter69) — frontend uses this for the badge + filter.

**Frontend (`/app/frontend/src/pages/Admin.jsx`):**
- New filter pill `filter-outstanding-balance` next to the search bar, shows `N with open balance` when any member has total > 0. Click toggles narrowing.
- Per-row checkbox column (`select-member-{id}`) + header select-all (`select-all-visible`). `selectedIds` is a `Set` keyed by user id so selection survives filter/search changes.
- Selection actions strip shows `N selected` counter + `+ Add anniversary fee to N` button + `Clear`.
- Bulk dialog (Dialog with `bulk-line-label` / `bulk-line-amount` / `bulk-confirm`) prefilled with "10-Year Anniversary Fee" / $150 and a clear duplicate-skip explainer.
- `$X owed` badge (`owes-badge-{id}`) renders in each row's name cell when total > 0.

**Verification (iteration 71):**
- 12/12 new pytest cases pass (`test_iteration71_bulk_add_line.py`): happy path, idempotency (case-insensitive), mixed valid/bogus ids, 422 validation, member-auth rejection (403), GET /members surfaces total.
- 11/11 iter69 + iter70 regression tests still pass.
- Full E2E UI flow verified by testing agent: select 3 rows → confirm → 3 `$75.00 owed` badges → filter pill narrows view → cleanup via DELETE 200.


### Phase BL — Iteration 70: Fix "Member doesn't see Zeffy link on profile" (2026-02-15)

**Bug report:** Members weren't seeing the per-member Zeffy link on their /profile after admin "set" it.

**Root cause:** The Zeffy URL field had its OWN dedicated endpoint (`PUT /admin/members/{id}/balance/zeffy-url`) — by design, since the main `PUT /members/{id}` does not touch `outstanding_zeffy_url` (security boundary). The in-section "Save URL" button was the only path that committed the URL, but admins naturally clicked the dialog's bottom "Save changes" button after pasting the URL → silent data loss.

**Fix** (`/app/frontend/src/components/MemberBalanceEditor.jsx`):
- URL input now auto-saves silently on **blur** and on **Enter** (Enter triggers blur).
- 3-state status badge next to the label: `Unsaved · auto-saves on blur` → `Saving…` → `Saved` so the admin can see the persistence state at a glance.
- Explicit "Save URL" button preserved but disabled when input matches server value (no-op guard).
- Help text under the field explicitly calls out that the bottom Save Changes button does NOT save this field.

**Verification (iteration 70):**
- 6/6 UX scenarios pass: auto-save on blur, end-to-end visibility on member profile, URL-set-but-no-lines edge, Save-URL button state, clear-URL via blur, backend security boundary.
- 10/10 iter69 regression tests still pass.
- New `/app/backend/tests/test_iteration70_zeffy_url_isolation.py` proves PUT `/members/{id}` cannot mutate `outstanding_zeffy_url` even with injected payload.


### Phase BL — Iteration 69: Outstanding-balance lifecycle for 10-year anniversary (2026-02-15)

**User request:** "We have a 10 year anniversary and members still have outstanding balances. We use Zeffy, and we want to add a Zeffy link to individual profiles for them to make payments." Confirmed scope: per-member Zeffy URL, multi-line balance, admin-set per-member, both confirmation flows (admin mark-paid + member-submit-receipt), does NOT extend membership.

**Backend** — new module `/app/backend/routes/balances.py` registered onto `/api`:
- Storage embedded on `users`: `outstanding_zeffy_url`, `balance_lines[]` (each line carries id, label, amount, created/paid metadata).
- Routes:
  - `GET /admin/members/{id}/balance` — read
  - `PUT /admin/members/{id}/balance/zeffy-url` — set per-member URL (https-only)
  - `POST /admin/members/{id}/balance/lines` — add line
  - `PUT/DELETE /admin/members/{id}/balance/lines/{line_id}` — edit / remove unpaid line
  - `POST /admin/members/{id}/balance/lines/{line_id}/mark-paid` — admin clears one line + creates `transactions` record (purpose=balance, provider=zeffy, status=completed)
  - `PUT /admin/transactions/{tx_id}/approve-balance` — admin approves a member-submitted receipt and stamps the linked line(s) paid
  - `GET /me/balance` — member reads own balance + pending receipts
  - `POST /me/balance/submit-receipt` — member confirms Zeffy payment for chosen line(s); creates PENDING transaction; double-submit blocked
- User serializer extended with `outstanding_zeffy_url` and computed `outstanding_balance_total`.

**Frontend** — two new components:
- `/app/frontend/src/components/MemberBalanceEditor.jsx` — embedded in Admin → Members → Edit. Shows URL field with save, pending-receipts panel with one-click approve, open lines with edit/mark-paid/delete, add-line form, and collapsible payment history.
- `/app/frontend/src/components/MyOutstandingBalance.jsx` — rendered on Profile right below the dues block (auto-hides when total = 0). Shows total, "Pay via Zeffy" CTA opening the per-member URL, line checkboxes, and a receipt-submission form. Lines tied to a pending receipt are locked to prevent double-submit.

**Verification:**
- 10/10 pytest cases pass (`test_iteration69_outstanding_balance.py`): URL set + https guard, line CRUD, mark-paid creates the transaction, edit/delete on paid lines blocked (400), member-only auth, admin-only auth, member submit + admin approve flow, double-submit blocked, paid-line submission blocked.
- Live end-to-end curl flow validated (admin → 2 lines → member submit → admin approve → admin mark-paid → total $0).
- Screenshots confirm both member and admin views render correctly.

**Notes:**
- Membership lifecycle (`membership_expires_at`) is intentionally untouched by this flow (user choice #5a).
- Paid lines are preserved on the user doc as immutable history (so members and admins see receipts); only unpaid amounts sum into `outstanding_balance_total`.


### Phase BL — Iteration 68: CSV importers accept name in lieu of email (2026-02-15)

**User request:** "When uploading CSV files, allow to add either full names, or first and last names in lieu of the email address because the members use different email addresses." User-chosen options: apply to both Hours + Donations; ambiguous names → ERROR (admin must add email); exact case-insensitive matching.

**Changes:**
- New `/app/backend/routes/_csv_member_lookup.py` — shared helper. Pre-fetches all candidate users in ONE Mongo round-trip and resolves each row in-memory.
- `/app/backend/routes/hours.py` — `/api/hours/admin/csv` now accepts `member_email` OR `full_name` OR (`first_name`+`last_name`). Template + header validation updated. Preview rows include `matched_by`.
- `/app/backend/routes/donations.py` — `/api/donations/admin/csv` mirror-changes. Adds `member_identifier` to preview rows so the UI can label the source.
- `/app/frontend/src/pages/Hours.jsx` + `Admin.jsx` — help text spells out the three lookup paths + ambiguity warning. Donations preview row label falls back to identifier when email is empty.
- Tests: 16 new pytest cases in `/app/backend/tests/test_iteration68_csv_member_lookup.py` covering all four resolution paths + priority ordering + ambiguity.

**Resolution semantics:**
1. `member_email` present → exact case-insensitive match. NOT found ⇒ error (does NOT silently fall through to name, since that would hide typos).
2. `full_name` present → exact case-insensitive on `users.name`. >1 match ⇒ "ambiguous: N members named '…'. Add a 'member_email' column to disambiguate."
3. `first_name`+`last_name` present → exact case-insensitive on `users.first_name` AND `users.last_name`. Same ambiguity rule.
4. None present ⇒ "row is missing a member identifier".

**Verification:** Backend pytest 16/16 pass. End-to-end curl dry-run validated all four paths and the ambiguity error (seeded two "Collision Twin" users) on both Hours and Donations. UI screenshot confirms the new help-text dialog renders correctly.


### Phase BL — Iteration 67: Inactive-member guard + 15-day grace + date-display TZ fix (2026-02-15)

**User requests addressed:**
1. Off-by-one calendar-day display on Admin Members `membership_expires_at` and Hours `service_date` (e.g. Nov 11 showing as Nov 10 in EST because the value was UTC midnight).
2. Auto-flip members to `status_override='inactive'` after 15 days past dues expiry (was 30).
3. Restrict inactive members to Home + Profile only — both client-side (nav hidden + redirect) and server-side (API 403).

**Changes:**
- `/app/frontend/src/lib/dateUtil.js` — new `formatCalendarDay(iso, pattern)` helper that strips the time portion and parses as local midnight so the displayed calendar day matches what the submitter typed (TZ-safe). Wired into Admin Members expiration column and Hours rows.
- `/app/backend/server.py` L30 — `GRACE_PERIOD_DAYS = 15` (was 30). `_auto_inactive_loop` (L5007-5028) uses the constant to flip stale members nightly.
- `/app/backend/server.py` L5455-5533 — new `block_inactive_member_writes` HTTP middleware + `INACTIVE_ALLOWED_PREFIXES` / `INACTIVE_ALLOWED_EXACT` allow-lists. Admins always bypass; inactive members get 403 for any non-allowlisted `/api/*` path. Allow-list covers auth, `/api/me*`, `/api/files/*`, `/api/photos*`, `/api/news`, `/api/chapters`, `/api/causes`, unsubscribe links, health.
- `/app/frontend/src/components/ProtectedRoute.jsx` — new `allowInactive` prop; inactive non-admins on any non-allowlisted route redirect to `/`.
- `/app/frontend/src/components/Navbar.jsx` — hides every nav link except Home + Profile for inactive non-admins and surfaces a red `data-testid='inactive-membership-banner'` strip.

**Verification (iter67):**
- Backend pytest `/app/backend/tests/test_iteration67_inactive_member_guard.py` — 14/14 pass.
- Inactive member: allow-listed endpoints succeed; `/api/members`, `/api/hours`, `/api/events`, `/api/donations` all return 403 with "membership is inactive".
- Admin with `status_override='inactive'` still bypasses (verified non-403).
- Active-member regression: no false blocks.
- Cron logic: user with `expires_at = now-20d` flipped to inactive; `now-5d` not flipped.
- Frontend: inactive maya redirected from `/hours` and `/events` to `/`; banner visible; nav stripped to logo. Admin Members table shows `'Dec 31, 2025'` (was `Dec 30`) for `2025-12-31T00:00:00Z`.

**Known cosmetic nits (not bugs):**
- `INACTIVE_ALLOWED_PREFIXES` lists `/api/health` though the actual health route is `/health`. Middleware only intercepts `/api/*` so this is dead-but-harmless.
- `INACTIVE_ALLOWED_EXACT` contains `/api/auth/me` + `/api/auth/logout` which are already covered by the `/api/auth/` prefix — redundant.



### Phase BL — Iteration 69: Email module extraction + stale test refresh (2026-06-22)
The biggest extraction yet.

1. **Email routes moved to `/app/backend/routes/email.py`** — 24 routes + 7 Pydantic models + 3 serializers + 5 built-in starter templates + the seed function. Single `register(...)` callable wired in next to the other route modules.
   - **Routes lifted**: `/email/templates` CRUD, `/email/preview`, `/email/blast`, `/me/email-preferences` (GET/PUT), `/email/blasts`, `/email/blasts/{id}/failed`, `/email/drafts` CRUD, `/email/password-setup-failures`, `/email/unsubscribe`, `/email/resubscribe`, `/email/unsubscribe-status`, `/email/deliverability`, `/email/test-send`, `/email/webhook`, `/email/signatures` CRUD, `/email/upload-image`.
   - **Helpers lifted**: `render_template` (renamed `render_variables` inside the module), `resolve_segment`, `template_out`, `_draft_out`, `_signature_out`, all the request models, `BUILTIN_EMAIL_TEMPLATES`, `seed_builtin_email_templates`.
   - **Kept in server.py** (shared with chat-digest and automated-emails): `send_bulk_email`, `_normalize_email_images`, `_verify_unsubscribe_token`, `RESEND_*` constants, `resend_sdk`, `put_object`, `IMAGE_EXT`, `MIME_BY_EXT`. These are injected into `register(...)`.
   - **Startup hook** updated: `await _routes_email.seed_builtin_email_templates(db, iso, now_utc, logger)`.
   - `server.py` is now **5431 lines** (down from 6233 → **−802 lines, −13%** in a single extraction).

2. **Stale award test assertions refreshed** so the CI suite is fully green for awards:
   - `test_fraternity.py::test_awards_seeded` — was checking for the original demo seed (Founder's Medal, Service Star, etc.) which admins have since replaced with real fraternity ribbons (Life Membership Ribbon, etc.). Test now verifies the endpoint returns ≥1 award with the count fields present.
   - `test_fraternity.py::test_award_grant_revoke_flow` — was asserting duplicate grant returns 400, contradicting Iter 36's "multiple grants per member" feature. Test now asserts the second grant gets ordinal 2 and a new id.
   - `test_iteration49_award_grants_endpoint::test_seeded_award_returns_enriched_rows` — expected exactly 5 grants but admins have granted more since the seed; relaxed to ≥5.

3. **Verification**:
   - All 50 iter64 / iter65 / phase_bc tests pass.
   - All 8 award tests pass (1 expected skip).
   - Manual curl probe of `/api/email/templates`, `/drafts`, `/blasts`, `/signatures`, `/deliverability`, `/me/email-preferences` all return 200 with correct payloads.



### Phase BK — Iteration 68: CI frontend build + Awards extraction (2026-06-22)
Two infrastructure wins from the standing P1/P2 list.

1. **CI workflow now builds the frontend** (`.github/workflows/ci.yml`)
   - Renamed workflow from "Backend pytest" → "CI" to reflect the broader scope.
   - Added a parallel `frontend` job: Node 20, `yarn install --frozen-lockfile`, `yarn build`.
   - Uses `CI=false` for the build step because the codebase still has ~24 pre-existing `react/no-unescaped-entities` ESLint warnings that CRA would promote to errors under `CI=true`. The build still catches the bugs that matter (syntax errors, broken imports, missing modules, JSX errors). Tracked: re-enable `CI=true` once cosmetic warnings are cleaned.
   - Verified locally: `yarn build` succeeds in ~44s, produces a 579 KB gzipped bundle.

2. **Awards routes extracted to `/app/backend/routes/awards.py`**
   - Moved 9 routes + the `award_out` serializer (255 lines lifted from `server.py`).
   - Endpoints owned by the new module: `GET /awards`, `GET /awards/{id}/grants`, `POST /awards`, `PUT /awards/{id}`, `DELETE /awards/{id}`, `POST /awards/{id}/grant`, `POST /awards/{id}/grant-bulk`, `DELETE /awards/grants/{id}`, `PUT /awards/grants/{id}`, `GET /members/{id}/awards`, `GET /me/awards`.
   - Registered via `routes_awards.register(api, db=, admin_tab_dep=, get_current_user=, iso=, now_utc=)` next to the other route modules.
   - `reconcile_awards` (startup data fixer) stays in server.py — it's a one-time migration helper, not a route.
   - `server.py` is now 6233 lines (down from 6488; -4% in one extraction).
   - All 18 iter64+65 tests still pass. Manual curl probe of `/api/awards` and `/api/me/awards` returns 200. The 3 pre-existing failures in `test_fraternity.py` + `test_iteration49_award_grants_endpoint.py` are data-drift issues unrelated to this refactor (verified by running on HEAD before changes — same failures occurred).



### Phase BJ — Iteration 67: Year filters back to 2017 + Admin.jsx toast hardening (2026-06-21)
Two small but high-impact polishes.

1. **Year filters extended to 2017** — for years the chapter has been active (founded ~2017). The Year `<Select>` on member-facing pages used to cap at 4–5 years back, which silently hid older records.
   - `pages/Hours.jsx`: My Hours year filter — was `[current, -1..-4]`, now `[current..2017]`.
   - `pages/Profile.jsx`: Tax-letter year picker — was `[current..current-5]`, now `[current..2017]`.
   - Already correct (no change needed): `Transactions.jsx`, `Reports.jsx` (Hours/Donations/Awards filters), and backend endpoints (no min-year restriction was ever enforced server-side).

2. **Admin.jsx toast hardening (P1 sweep)** — wrapped every `(?:e|err|ex)\.response\?\.data\?\.detail` reference in Admin.jsx with `formatApiError(...)` from `lib/api.js`. 37 call sites (38 incl. the iter66 fix) so any future endpoint that returns a FastAPI 422 validation array can no longer crash the React tree with `Objects are not valid as a React child`. `formatApiError` already handled strings/arrays/objects-with-`.msg` — we just had to apply it consistently.



### Phase BI — Iteration 65/66: Email drafts, per-template test send, failure surfaces (2026-06-21)
Three admin productivity wins on the Email tab, plus a critical 422-crash defense.

1. **Per-template "Send test to me" button** (Admin → Email → Templates)
   - Every template card now has a `Send test to me` button (`template-test-send-<id>`) that fires `POST /api/email/test-send` with just the `template_id`. Backend `EmailTestSendIn.to_email` is now `Optional[str]` and falls back to the calling admin's email address — so one click confirms the template renders in inbox before a real blast.
   - Built-in templates display a "Built-in" badge next to the name.

2. **Draft auto-save + manual saves** (Admin → Email → Compose)
   - New collection `email_drafts` (private per admin) with CRUD endpoints `GET/POST/PUT/DELETE /api/email/drafts`.
   - Auto-save: every subject/body/segment/tier/individual change triggers a 2-second debounced upsert to a single per-admin auto-save slot (`is_autosave=true`). The `visibilitychange`, `beforeunload`, and `pagehide` events also force an immediate flush — switching tabs, closing the window, or accidentally clicking another tab never loses work.
   - Manual saves: `Save as draft` button prompts for a name and creates a separate named draft. The Drafts toolbar shows a Load picker (auto-save + named drafts) and a destructive-coloured Delete picker (named drafts only). Auto-save status indicator displays "Saved at HH:MM" / "Saving…" / "Save failed".

3. **Failed-recipient visibility** (Admin → Email → History)
   - Each historical blast with `failed_count > 0` now shows the count as a clickable destructive-coloured button. Clicking expands the row to show every failed recipient's email + reason, plus a `Copy N emails` button that puts a comma-separated list on the clipboard for one-click pasting elsewhere.
   - New endpoint `GET /api/email/blasts/{id}/failed` exposes the full failed list.
   - New "Password-setup link failures" section below the blast table — sourced from `db.password_setup_attempts` (newly written by both `/api/admin/members/{id}/resend-set-password` and `/api/admin/members/bulk-resend-set-password`). Shows attempted timestamp, member name, email, reason, attempting admin (mode=single|bulk) for last 90 days. Includes Copy + Refresh buttons.

4. **Critical bug fixed mid-iteration (iter66)**: Initial implementation of (1) crashed the Admin page with `Objects are not valid as a React child` when backend returned a 422 validation error (FastAPI returns `detail` as an array of objects). Two-pronged fix:
   - Backend: `EmailTestSendIn.to_email` made `Optional[str] = None` with admin-email fallback — the omitted-to_email path now returns 200.
   - Frontend: Admin.jsx imports `formatApiError` from `lib/api.js` and coerces all `detail` values to string before passing to `toast.error`.

5. **Regression**: `/app/backend/tests/test_iteration65_drafts_failures.py` (9 tests covering drafts CRUD + auto-save upsert + ownership + blast failed list + password-setup-failures + test-send with/without to_email). All 18 iter64+65 tests pass.



### Phase BH — Iteration 64: Email Blast Composer overhaul (2026-06-21)
Three improvements for admin email blasts: resizable images, reliable email rendering, and pre-built templates.

1. **Resizable images in TipTap RichEditor**
   - New `/app/frontend/src/components/ResizableImage.jsx` — TipTap node extension extending the default Image with:
     - `width` (int) + `align` ("left"|"center"|"right") attributes.
     - React NodeView with drag handles on all 4 corners (`ri-handle-tl/tr/bl/br`) for visual resize (60–1200px clamp).
     - Floating toolbar on selection (`ri-toolbar`): alignment (`ri-align-left/center/right`), size presets `S=200` / `M=400` / `L=600` / `Full` (`ri-size-s/m/l/full`), and a remove button (`ri-remove`).
     - Live width label badge shows current px while resizing.
     - Renders email-safe HTML: `<div data-image-align="..."><img src="..." width=... style="max-width:100%;height:auto;display:inline-block;border-radius:8px;width:Xpx"></div>`.
   - `/app/frontend/src/components/RichEditor.jsx` now uses `ResizableImage` (replaces `@tiptap/extension-image`); inserts new images at `width=400, align="center"` by default.

2. **Email image normalization** (`/app/backend/server.py` `_normalize_email_images`)
   - Rewrites relative `/api/...` URLs to absolute via `FRONTEND_URL` env (Gmail/Outlook proxies need absolute).
   - Strips `class=` attributes on `<img>` tags (email clients ignore CSS classes; Tailwind classes leak from old blasts → broken render).
   - Ensures every img has inline `max-width:100%` + `height:auto`.
   - Idempotent — safe to call repeatedly.
   - Applied in both `send_bulk_email` (real send) and `email_preview` (admin's live preview matches recipient view).

3. **Pre-built email templates** (`/app/backend/server.py` `seed_builtin_email_templates`)
   - 5 starter templates seeded on startup with stable ids and `is_builtin=true`:
     - `builtin_tpl_announcement` — General Announcement
     - `builtin_tpl_event_reminder` — Event Reminder
     - `builtin_tpl_dues_reminder` — Dues Reminder
     - `builtin_tpl_welcome` — Welcome New Member
     - `builtin_tpl_newsletter` — Monthly Newsletter
   - Each is brand-styled (#C8102E / #0A2463), inline-styled (no CSS classes), and uses `{{first_name}}` variable.
   - Admins can edit and delete them via the existing Templates tab (full CRUD).
   - `template_out` now includes `is_builtin` flag in API response.

4. **Bug fix bonus**: Restored the missing `@api.get("/email/blasts")` decorator on `list_email_blasts` — endpoint was returning 404 since a previous refactor removed the route line.

5. **Regression**: `/app/backend/tests/test_iteration64_email_composer.py` (10 tests) + `/app/backend/tests/test_iteration64_email_extra.py` (6 tests, added by testing agent). All 16 pass. Frontend smoke verified all data-testids resolve and resize/align/preset interactions work.



### Phase BG — Iteration 63: Show full photo everywhere (object-contain sweep) (2026-06-21)
Per user request — every uploaded photo across the site now displays in full (no cropping). Sweeping global change: replaced `object-cover` with `object-contain` on every `<img>` across the React frontend (40 occurrences in 19 files: pages Gear, News, NewsDetail, Donations, Documents, Chapters, Photos, Omega, Home, Profile, Admin, Reports, Chat + components TopDonorsLeaderboard, CommunityServiceLeaderboard, AvatarUploader preview image, Navbar logo, PageBuilder, BlockRenderer).

Kept `object-cover` ONLY on the live webcam `<video>` preview inside `AvatarUploader.jsx` — that's a camera feed, not an uploaded photo, and stretching the live frame would distort it during capture.

**Verification (iter63)**:
- Grep guarantee: only 1 remaining `object-cover` reference site-wide (the webcam video).
- UI smoke `/gear`: 8/8 product images now render `object-contain`, 0 `object-cover`. Visually confirmed — Blazer Depot logo, AOP gold seal, and apparel photos all show edge-to-edge inside their tiles with neutral letterboxing where aspect ratios don't match.
- No backend changes; no test regression.

**Note**: with `object-contain` the cards may show empty letterbox bars when an uploaded photo's aspect ratio doesn't match the tile. If that becomes visually distracting on specific surfaces, we can revisit per-surface (e.g. keep avatar circles cropped while leaving Gear/News cards in contain mode).



### Phase BF — Iteration 62: Chat email digest extraction (2026-06-21)
Last big extraction off the P1 list. Moved the chat-email-digest service out of `server.py` into its own module and fixed a latent runtime bug along the way.

1. **`/app/backend/routes/chat_digest.py`** (new, 212 lines) owns:
   - Constants: `CHAT_DIGEST_DELAY_SECONDS` (15-min debounce).
   - Public: `queue_chat_notifications(conv, message, sender)` — called by `routes/chat.py::send_message` on every new message; `start_chat_digest_loop()` — idempotent task starter.
   - Private: `_send_chat_digest_email`, `_send_chat_digest_sms`, `_chat_digest_loop` (60-second tick), `_html_escape`.
   - Module-level `_db, _iso, _now_utc, _RESEND_API_KEY, _RESEND_FROM, _resend_sdk, _send_sms, _logger` populated via `register(...)` at app startup.
2. **`server.py`**: 6221 → 6085 lines (~140 lines moved). The old block is replaced by a 4-line stub that re-exports `queue_chat_notifications` + `CHAT_DIGEST_DELAY_SECONDS` for legacy callsites. The startup task block now calls `routes_chat_digest.register(...)` followed by `start_chat_digest_loop()`.
3. **Latent bug fix**: the pre-extraction code referenced an undefined `_now_iso()` at three call sites inside `queue_chat_notifications` and `_chat_digest_loop`. Those would have raised `NameError` the first time the loop iterated or a chat message was actually queued for digest. Replaced with the configured `_iso(_now_utc())` calls.

**Verification (iter62)**:
- Curl smoke (admin → member DM, single message):
  - `queue_chat_notifications` wrote 1 pending row with the correct `due_at` (created_at + 15 min)
  - Member `/conversations/{cid}/read` flipped the row status from `pending` → `cancelled` (this read-receipt cancellation was the path most affected by the latent NameError bug — now provably working).
- Pytest: 90/91 pass across iter5*+iter6* (1 pre-existing test bug in iter50 RSVPs unrelated to chat: asserts `400` but FastAPI returns Pydantic's `422` for missing required field).
- Server.py size milestone: **6085 lines** (down from 6912 at session start — −827 lines across iter53/55/60/62 extractions).

### server.py size progression (since session start)
| iter | event | size | delta |
|------|-------|------|-------|
| 51 (start) | — | 6912 | — |
| 53 | gear → routes/gear.py | 6755 | −157 |
| 55 | chat REST + WS → routes/chat.py | 6323 | −432 |
| 60 | donations/causes → routes/donations.py | 6220 | −103 |
| **62** | **chat digest → routes/chat_digest.py** | **6085** | **−135** |



### Phase BE — Iteration 61: Donations report mirrors Hours report (2026-06-21)
Made the admin Donations report structurally identical to the Hours report — same filters, same view pills, same totals strip — so the muscle memory transfers and admins can answer "how much has this member donated?" in one click.

1. **Backend** (`routes/reports.py`): new `GET /reports/donations/summary` mirroring `/reports/hours/summary`.
   - Filters: `year`, `quarter`, `month`, `chapter_id`, `cause_id`, `status_filter`.
   - `group_by` ∈ {`member`, `chapter`, `month`, `quarter`, `year`} — sums `amount`, counts gifts.
   - `totals` block: `completed_amount`, `pending_amount`, `refunded_amount`, `*_count`, plus `donor_count` (unique completed-donation user_ids).
   - Chapter scope still auto-applied for chapter-scoped admins.
2. **Frontend** (`Reports.jsx::DonationsReport`): rebuilt as a clone of `HoursReport`.
   - **Filters**: Year (back to 2017), Period (Entire year / Q1-Q4 / Jan-Dec), Chapter, Status, Cause.
   - **View pills**: Individual entries · By member · By chapter · By period.
   - **Totals strip**: Completed / Donors / Pending / Refunded (only when grouped view is active, identical to Hours).
   - **Tables**: per-view headers matching Hours conventions — "By member" exposes the at-a-glance per-donor total (`Total donated` column + `Gifts` count) sorted descending. CSV export per view.
   - Testids: `donations-report`, `donations-filter-{year,period,chapter,status,cause}`, `donations-view-{entries,by-member,by-chapter,by-period}`, `donations-by-member-row-{user_id}`, `donations-by-chapter-row-{cid}`, `donations-by-period-row-{key}`, `donations-totals`.

**Verification (iter61)**:
- `tests/test_iteration61_donations_summary.py`: 7/7 pass — group_by=member sums + sorts desc, group_by=chapter shape, group_by=month buckets sorted ascending, totals block keys, quarter filter, month filter, non-admin 403. Plus all 6 iter59 filter tests continue to pass.
- UI smoke: opened all 4 view pills on /admin → Reports → Donations and confirmed each renders the right header set + totals strip + filter row.



### Phase BD — Iteration 60: Donations/Causes extraction (2026-06-21)
P1 modularization continued — the entire donations + causes block left server.py.

1. **`/app/backend/routes/donations.py`** (new, 475 lines) owns:
   - Pydantic models: `CauseIn`, `CauseUpdateIn`, `PledgeIn`.
   - Helpers: `cause_out` (serializer), `recompute_cause_totals` (cause totals refresher).
   - REST endpoints: `GET /causes`, `GET /causes/{id}`, `POST /causes`, `PUT /causes/{id}`, `DELETE /causes/{id}`, `POST /causes/{id}/pledge`, `GET /causes/{id}/donations`, `GET /donations/admin/csv/template`, `POST /donations/admin/csv`, `GET /leaderboards/top-donors`.
   - `re.escape` is used for the email regex match (replacing the previous `_re_escape_local` shim in server.py).
2. **`server.py`** shrank ~430 lines (6648 → 6220). The old block is replaced by a 4-line stub that re-exports `recompute_cause_totals` and `cause_out` so the PayPal capture flow (still in server.py at line 4105) can keep importing them via the same import path. Registration threads `admin_tab_dep`, `is_chapter_scoped`, and `chapter_scope_user_ids` into `routes_donations.register(api, …)`.

**Verification (iter60)**:
- 50/50 pytest pass across iter52, iter53, iter54, iter56, iter57, iter59 regression suites — no regressions.
- Curl smoke: `GET /causes` (3 causes), `GET /leaderboards/top-donors` (responds with proper period_label/empty lists since prior test data was cleaned up), `GET /donations/admin/csv/template` (returns canonical header).

### server.py size progression
- iter51 end: 6912 lines
- iter53 (gear extraction): 6755 (−157)
- iter55 (chat extraction): 6323 (−432)
- **iter60 (donations extraction): 6220 (−103)**

Remaining sizable extraction targets: chat email digest service (~210 lines, lines ~4900–5100), automated email cron + scheduler, and the ~150-line ICS/calendar block.



### Phase BC — Iteration 59: Donations filter parity with hours + member year filter (2026-06-21)
Closed the loop on donation visibility — admins can now slice donations by the same axes as volunteer hours, members can scope their receipts to any single year.

1. **`/api/reports/donations`** gained `user_id`, `chapter_id`, `year`, `quarter`, `month`, `from_date`, `to_date` query params (mirroring `/reports/hours`). Date range filtering happens on `created_at`; chapter scope expands to all member ids of the chapter and intersects with any explicit `user_id`. Chapter-scoped admins still get their automatic restriction.
2. **`/api/me/transactions`** accepts an optional `year={YYYY}` query param. Omit it for the lifetime list (existing default).
3. **Admin → Reports → Donations UI** (`Reports.jsx::DonationsReport`): grid now exposes Cause / Status / Member / Chapter / Year filters; Year picks descend from current year back to 2017 (or "All years"). New `causeDisplay(t, causes)` helper resolves the **Cause column**: cause title when linked, `"<label> (unallocated)"` when only `cause_label` is present (CSV-imported, no matching cause), `—` otherwise. CSV export of the report uses the same resolver. Empty result row added.
4. **Member receipts (`Transactions.jsx`)**: third filter "Year" added alongside Type and Status. State change triggers a fresh `/me/transactions?year=…` fetch (server-side filter, not just a client filter — keeps the 500-row API limit honest).

**Verification (iter59)**:
- `tests/test_iteration59_donations_filters.py`: 6/6 pass — filter by user_id, chapter_id, year (positive + negative case), quarter+month, /me/transactions year filter, cause_label round-trips on unmatched CSV imports.
- UI smoke: Admin Reports → Donations renders the 5 filters with proper data sources; member /transactions exposes the year picker.



### Phase BB — Iteration 58: Donations CSV — cause truly optional + free-text label preserved (2026-06-21)
Hotfix on iter56's bulk donations importer based on user feedback ("Make the cause optional").

- `POST /api/donations/admin/csv`: a non-blank `cause` value that does NOT match any existing cause is no longer an ERROR. The row imports as READY with a non-blocking `warnings` array (`"cause '...' not found — saved as unallocated"`), `cause_id=null`, and the original free-text label is preserved in the transaction `description` as `Fund: <label> · <note> · (CSV import)` plus a dedicated `cause_label` field. Blank cause stays unallocated as before. Matched cause links and updates `cause.raised_amount` as before.
- Admin UI: dialog hint rewritten to "cause is optional — leave blank OR enter any text; matching links to that cause, non-matching is saved as unallocated with the label preserved." Preview rows render a yellow ⚠ row beneath status when a `warnings` entry is present.
- **History tracking confirmed end-to-end**: imported donations show up in `/api/reports/donations` (admin), `/api/me/transactions` (member receipts), `/api/causes/{id}/donations` (per-cause), and the home Top Donors leaderboard — exactly like the volunteer-hours flow. No new history endpoints needed; the existing transactions collection already powers all four surfaces.

**Verification (iter58)**:
- `tests/test_iteration56_donations_csv.py` re-tightened: `test_real_import_writes_only_valid_rows` now expects 2 successful rows out of 5 (matched + unmatched cause both succeed), with the unmatched cause carrying a `warnings` entry but no `errors`.
- New `test_unmatched_cause_preserves_label_in_description` asserts the free-text label survives in `/reports/donations`.
- 16/16 pass (8 iter56 + 8 iter57).



### Phase BA — Iteration 57: Per-cause payment processor (PayPal vs Zeffy) (2026-06-21)
Admins can now route funds for each individual cause through either PayPal (in-app checkout) or Zeffy (external link).

1. **Backend** (`server.py`): `CauseIn` and `CauseUpdateIn` gain two new fields — `payment_processor: Literal["paypal","zeffy"] = "paypal"` and `zeffy_url: str = ""`. `cause_out` exposes both fields on every read. Invalid processor values get a 422 from Pydantic. Existing causes default to PayPal because the model's default is `"paypal"`.
2. **Frontend (Admin `CauseDialog`)**: New "Receive funds via" section with two pill buttons (`cause-processor-paypal`, `cause-processor-zeffy`). When Zeffy is selected, a `cause-zeffy-url-input` Input + helper hint appear with a Zeffy placeholder. `emptyCause()` initializes the new fields.
3. **Frontend (`Donations.jsx` `CauseCard`)**: If `cause.payment_processor === "zeffy"` AND a `zeffy_url` is set, the Donate button becomes an `<a target="_blank">` link (`zeffy-donate-{id}`) that opens the admin-supplied Zeffy form in a new tab. Otherwise the existing `PledgeDialog` (in-app PayPal checkout) is used.

**Verification (iter57)**:
- `tests/test_iteration57_cause_processor.py`: 8/8 pass — Zeffy create/persist, paypal default, invalid processor → 422, processor flip + zeffy_url clear, list endpoint surfaces new fields, non-admin 403 on create/update, partial update preserves processor + url.
- UI smoke: Admin Causes → New cause dialog renders both pills, switching to Zeffy reveals the URL input with the right placeholder; preserved settings reflected on save.



### Phase AZ — Iteration 56: Bulk donations CSV + Top Donors leaderboard (2026-06-21)
Two coordinated changes around donations:

1. **Bulk CSV upload for donations** (admin):
   - `GET /api/donations/admin/csv/template` — returns a 7-column CSV (`member_email, amount, cause, date, note, anonymous, method`) with a sample row.
   - `POST /api/donations/admin/csv?dry_run=true|false` — parses uploads, resolves email→user and cause-title→cause_id (case-insensitive), validates each row, and returns a row-by-row preview with READY/ERROR pills. On confirm, writes `db.transactions` records (status=completed, type=donation, anonymous flag respected) and refreshes raised_amount/donor_count on every touched cause. Date column accepts the same flexible formats as the hours CSV (YYYY-MM-DD, MM/DD/YYYY, M/D/YY, 15-Jun-2026).
   - Admin UI: new "Bulk import donations" button next to "New cause" on the Causes tab, opening a dialog with template download + file picker + dry-run preview + confirm. Testids: `donations-csv-btn`, `donations-csv-dialog`, `donations-csv-template-btn`, `donations-csv-file-btn`, `donations-csv-preview`, `donations-csv-row-{N}`, `donations-csv-confirm`.

2. **Top Donors Leaderboard** on the home page:
   - New `GET /api/leaderboards/top-donors?period={quarter|month|year|all}` aggregates completed donations by user_id and by chapter_id ($lookup), returning top-5 chapters and top-5 members with `amount` (sum) and `count` (gift count). Anonymous donations are excluded from the member board (privacy) but still counted in chapter totals.
   - New `<TopDonorsLeaderboard />` component on `/` rendered immediately below `CommunityServiceLeaderboard` under the same `showSection("leaderboard")` gate. Mirrors the community-service board's visual rhythm (gold/silver/bronze rank discs, avatar, member·chapter subtitle, rank rows in a single column) but in dollars. Two pill tabs to swap between Top Chapters and Top Members. Testids: `home-top-donors`, `top-donors-tab-chapters`, `top-donors-tab-members`, `top-donors-chapter-{id}`, `top-donors-member-{id}`.

**Verification (iter56)**:
- `tests/test_iteration56_donations_csv.py`: 7/7 pass — template header sanity, non-admin 403, dry-run never writes, real-import writes only the valid rows (1/5 in the test fixture, the other 4 ERROR with the right messages), leaderboard returns the expected shape, anonymous donations omitted from member board, quarter period label looks like `Qn YYYY`.
- UI smoke: Home `/` shows the new "Top Donors Leader Board · Q2 2026" section with Maya Patel $250 and Riley Chen $150 stacked under gold/silver discs. Admin Causes tab renders the new "Bulk import donations" button and the dialog opens with the right column hints + template link + file chooser.



### Phase AY — Iteration 55: Chat extraction (REST + WebSocket) (2026-06-21)
P1 modularization continued — the entire chat block left server.py.

1. **`/app/backend/routes/chat.py`** (new, 486 lines) owns:
   - `ChatHub` real-time fan-out class + the module-level singleton `chat_hub`.
   - REST endpoints: `GET/POST /conversations`, `GET/PUT/DELETE /conversations/{cid}`, `POST /conversations/{cid}/leave`, `POST /conversations/{cid}/read`, `GET/POST /conversations/{cid}/messages`, `DELETE /messages/{mid}`, `POST /chat/upload`.
   - WebSocket: `@app.websocket("/api/ws/chat")` — JWT cookie auth, ping/pong keep-alive, push-only server→client.
   - Pydantic models: `ConversationCreateIn`, `ConversationUpdateIn`, `MessageIn`.
   - Helpers: `conversation_out`, `message_out`, `_is_message_expired`, `_user_brief`, `_ttl_choice_to_seconds`.

2. **`server.py`** lost ~450 lines (6756 → 6323). The old chat block was replaced with a 9-line stub that just imports `chat_hub` from `routes.chat` so the chat-email-digest service (still in server.py) can keep checking who's connected. Registration at the bottom of server.py threads `queue_chat_notifications`, `jwt_secret`, `put_object`, `IMAGE_EXT`, `MIME_BY_EXT`, and `logger` into `routes_chat.register(api, app, ...)`.

**Verification (iter55)**:
- 50/50 pytest pass across iter51-54 regression suites — no regressions.
- Curl smoke: `GET /conversations` (3 returned), `POST /conversations` (DM created), `POST /messages` (delivered), `GET /messages` (last body matches `"iter55 smoke test"`), `POST /read` (ok), `DELETE /conversations` (ok), follow-up `GET` returns 404.
- WebSocket smoke (`wss://…/api/ws/chat`): cookie-auth succeeded, server sent `{"type":"connected","user_id":"…"}`, ping → pong roundtrip OK.



### Phase AX — Iteration 54: Admin full-edit of submitted hours (2026-06-21)
Admins now have a complete edit surface for every field on an existing volunteer-hours record — not just the hours value.

1. **Backend**: New `PUT /api/hours/{id}` admin-only endpoint backed by a new `AdminHoursEditIn` Pydantic model (every field optional). Only fields actually supplied (`exclude_unset=True`) are written. Hours-value changes stamp `hours_adjusted_by/_at`; status flips stamp `reviewed_by/_at`. Date is normalized through ISO before persistence. The existing `/hours/{id}/review` endpoint remains unchanged for the quick approve/reject flow.
2. **Frontend** (`Hours.jsx`): New `FullEditHoursDialog` component opened by a "⚙ Edit all" link next to the existing "✏️ Edit hrs" inline quick-fix in the admin Review queue. Surfaces every editable field (Hours, Date, Activity, Description, Event type, Status, Agency, Host name/phone/email, Admin note). Saves via `PUT /hours/{id}`, then reloads the queue. Testids: `edit-all-{id}`, `edit-all-dialog-{id}`, plus one per input (`edit-all-activity-{id}`, `edit-all-event-type-{id}`, `edit-all-save-{id}`, etc.).

**Verification (iter54)**:
- `tests/test_iteration54_admin_edit_hours.py`: 7/7 pass — every-field edit, partial-edit (no clobber), hours-only stamps adjustment audit, status-only stamps review audit, non-admin 403, unknown id 404, empty body no-op.
- UI smoke: dialog opened on Riley Chen's approved entry; every form field (Hours, Date, Activity, Description, Event type, Status, Agency, Host name/phone/email, Admin note, Save) rendered with correct prefilled values.



### Phase AW — Iteration 53: Admin dues-reminder summary email + Gear extraction (2026-06-19)
Two-part shipment:

1. **Admin dues-reminder summary email** — every time the daily dues-reminder cron fires, the existing `_send_dues_reminders(campaign)` (server.py) now collects each successful send into a `sent_records` list (`stage`, `stage_label`, `member_name`, `member_email`, `expires_at`). After the cycle finishes — and only if `total_sent > 0` — it dispatches a new transactional summary email via `_send_admin_dues_summary(campaign, sent_records)` to every admin (`role=admin`, valid email, `email_opt_out != True`). The summary email groups members by stage label (e.g. `30 days · 4 members`), and each row surfaces the member name + email + membership expiration date formatted as `Mon Day, YYYY`. Tagged `type=dues_admin_summary` / `campaign_id` for Resend deliverability tracking. Closes the audit loop: admins now know exactly who got pinged each cycle, including their renewal date.
2. **Gear endpoints extracted to `routes/gear.py`** — moved 7 endpoints + 3 Pydantic models + the `gear_out` serializer out of `server.py` (~157 lines deleted) into a focused 202-line module. `register(api, db, admin_tab_dep, iso, now_utc, put_object, image_ext, mime_by_ext)` is invoked from server.py's bottom-of-file include block. `server.py` is now ~6755 lines (down from 6912 at iter52). All gear flows (list, get, create, edit, delete, gear-page, image upload) confirmed working post-extraction via curl smoke.

**Verification (iter53)**:
- `tests/test_iteration53_dues_admin_summary.py`: 6/6 pass — covers one-email-per-admin dispatch, empty-records no-op, no-admin no-op, RESEND_API_KEY no-op, multi-record stage grouping (e.g. `30 days · 2 members`), and HTML escaping of member names.
- `tests/test_iteration52_admin_grant_hours.py`: 15/15 still pass — no regressions from the gear extraction.
- Gear CRUD smoke (curl admin session): create → update price → fetch → delete → 404 — all green.



### Phase AV — Iteration 52: Admin remove/update awards + multi-member grant + admin remove hours + ET event times (2026-06-19)
Four admin/member-card improvements shipped in a single iteration:

1. **Admin update/remove award grants** — new `PUT /api/awards/grants/{grant_id}` (accepts partial body `{granted_at?, reason?}`; date-only `YYYY-MM-DD` normalizes to ISO; empty body returns `{ok:true,no_change:true}`; invalid `granted_at` → 400) and `DELETE /api/awards/grants/{grant_id}` (admin-only, recalculates ordinal for surviving grants). Frontend `MemberCardDialog` renders `ribbon-edit-{id}` and `ribbon-remove-{id}` on each ribbon; `grant-edit-dialog` opens with `grant-edit-date`/`grant-edit-reason` inputs and `grant-edit-save` button. Remove fires a confirm() then DELETE.
2. **Multi-member award granting** — new `POST /api/awards/{award_id}/grant-bulk` (`{user_ids: [...], reason?, granted_at?}`, dedupes IDs, caps at 200, returns `{ok, created, failed, total}`). Frontend `GrantAwardDialog` was rewritten with multi-select checkboxes (`grant-member-checkbox-{id}`, `grant-clear-selected`, member count badge). Button text auto-updates to "Grant to N members" when ≥2 selected; calls `/grant` for 1 user, `/grant-bulk` for ≥2.
3. **Admin remove hours from member records** — new `DELETE /api/hours/{hours_id}` (admin can delete any user's hours; non-admin can only delete own). Approved-hours deletions correctly decrement `/me/hours/summary.total_approved` server-side. Frontend `Hours.jsx` Review queue surfaces `remove-hours-{id}` button next to Approve/Reject.
4. **Eastern Time enforcement for event displays** — added `/app/frontend/src/lib/eventTime.js` (`fmtET`, `fmtETDate`, `fmtETTime` powered by `date-fns-tz`). Replaces every `format(parseISO(...))` call across `Events.jsx`, `EventDetail.jsx`, `Calendar.jsx`, `Profile.jsx`, `Admin.jsx` dashboard timestamps so dates always render as EST/EDT (e.g. `8:00 PM EDT`) regardless of the viewer's browser TZ.

**Verification (iter52)**: testing_agent iteration_52.json — 15/15 backend pytest pass (5 update + 6 bulk-grant + 4 admin-delete-hours). Frontend ET labels confirmed live on `/events`, `/calendar`, `/admin`, `/events/{id}`. Main-agent visual smoke (this finalization pass) confirmed: multi-select grant dialog with "Grant to 2 members" button, member card showing 3 ribbons with Edit/REMOVE buttons, Hours Review queue rendering Remove button on a pending entry. New regression file at `/app/backend/tests/test_iteration52_admin_grant_hours.py`. No critical bugs; 4 low-priority review comments noted (e.g. `reason` type validation, chapter-scoped admin delete behavior) — left as documented future hardening.



### Phase AU — Iteration 51: Bulk RSVPs CSV + Hours CSV date parser fix (2026-06-19)
Two items in one shot:

1. **Hours CSV date parsing** — admins were hitting "Invalid date" on common Excel default formats. Replaced the brittle length-based parser with a new `_parse_csv_date()` helper in `routes/hours.py` that tries ISO + multiple US/Excel layouts: `%Y-%m-%d`, `%Y/%m/%d`, `%m/%d/%Y`, `%m-%d-%Y`, `%m/%d/%y`, `%m-%d-%y`, `%d-%b-%Y`, `%d-%b-%y`, `%d %b %Y`, `%d %B %Y`, `%b %d, %Y`, `%B %d, %Y`. Error messages now include the accepted formats so the admin can fix the file without trial-and-error. Frontend Hours CSV dialog help text gained a "Date formats accepted:" line.
2. **Bulk Import RSVPs** — new admin endpoints `GET /events/{id}/admin-rsvp/csv/template` and `POST /events/{id}/admin-rsvp/csv?dry_run=true|false&send_email=true|false`. CSV columns: `member_email` (required), `ticket_type` (optional), `guests` (semicolon-separated names), `guest_ticket_types` (parallel semicolon list). Rejects cancelled / paid / umbrella parent events with 400. Enforces capacity across the entire batch (running tally). Dedupes both DB-existing RSVPs and same-file duplicate emails. Frontend `AdminRsvpCsvDialog` mounted under "Admin tools" alongside the single-member admin RSVP dialog — reuses the dry-run preview UX (file selection → auto dry-run → row-by-row preview with READY/ERROR pills + guest pills → Confirm import). Email-suppression toggle for silent back-fills.

**Verification (iter51)**: testing_agent iteration_51.json — 22/22 backend pytest + all frontend Playwright checks PASS. New regression file at `/app/backend/tests/test_iteration51_bulk_rsvp_csv.py`. No bugs. Applied 1 inline comment from review (ordering note for the send_email=true attribution patch).



### Phase AT — Iteration 50: Admin RSVPs + member combined RSVP+guests email (2026-06-19)
Two related event-RSVP improvements:

1. **One combined email when members add guests** — previously a member RSVP fired a ticket email immediately, then adding guests via `PUT /rsvp/guests` fired a second email. Frontend `EventDetail.jsx` now drafts `pendingGuests` BEFORE the RSVP button, surfaces `GuestManager` in a new `pendingMode` (helper copy: "Bringing a +1? Add them now — you'll get one combined ticket email when you RSVP"), and includes the drafted guests in the single `POST /events/{id}/rsvp` call. RSVP button label updates to "RSVP — me + N guests".
2. **Admins can RSVP members + guests** — new `POST /api/events/{event_id}/admin-rsvp` endpoint (admin-only, `AdminRsvpIn` model). Stamps `created_by_admin` / `created_by_admin_name` on the rsvp doc. `send_email` flag (default true) lets admins suppress the ticket email for historical back-fills. Returns 409 if the member already has an RSVP. Frontend `AdminRsvpForMemberDialog` (visible only to admins on event detail page → "Admin tools" section, `data-testid=admin-add-rsvp-btn`) provides a searchable member picker with radio selection (excludes members who already RSVPed), inline guest rows, ticket-type select (when event allows tickets), and the email-suppression toggle.

**Verification (iter50)**: testing_agent iteration_50.json — 12/12 backend pytest + 11/11 frontend Playwright PASS. Network capture confirmed members now send a single POST with embedded guests (no follow-up PUT). Backend refactored after review to use a typed `AdminRsvpIn` Pydantic model instead of `dict` for proper OpenAPI/validation.



### Phase AS — Iteration 49: Clickable recipient counter on Awards Catalog (2026-06-19)
- **Backend**: new `GET /api/awards/{award_id}/grants` (member-auth) returns up to 500 enriched grant rows sorted granted_at DESC. Each: `{user_id, member_name, avatar_url, granted_at, year, ordinal, reason}`. Falls back to stored `user_name` (then "Former member") if the user has been deleted since the grant.
- **Frontend** (`Awards.jsx` `CatalogSection`): the "Granted to X members" footer on each catalog tile is now a button (with hover arrow affordance) when grants exist; tiles with 0 grants render "Not yet granted" as static text. Clicking opens `RecipientsDialog` which groups grants by year (newest first), showing avatar + name + ordinal pill (2×/3× for repeat awards) + Mon Day date. Rows clear on award switch so there's no stale-data flash.
- **Verification (iter49)**: testing_agent iteration_49.json — 6/6 backend pytest + 8/8 frontend Playwright PASS. Applied 2 minor defensive tweaks from the code review (member_name `or`-chain for departed-user edge case; `setRows([])` on award switch).



### Phase AR — Iteration 48: Tier chart correctness + Awards reports + Card photos (2026-06-19)
Three admin/member-facing fixes:

1. **"By Membership Tier" dashboard chart** — was showing the legacy `users.membership_tier` string column which defaulted to `"standard"` and surfaced `"lifetime"` for life members, even though neither is a real tier. Fixed by re-aggregating: group by `users.tier_id` → join `db.tiers` → return display name. Members with no `tier_id` or pointing to a deleted tier are excluded. New empty-state card (`tier-chart-empty`) renders a friendly 🏷️ "No members assigned to a tier yet" placeholder.
2. **Admin → Reports → Awards sub-tab** — new tab with two enriched audit tables:
   - **Award grants** (`/api/reports/award-grants`): every ribbon/medal grant sorted granted_at DESC, with current member name/email/avatar/chapter, award color dot, ordinal pill (3×, 2×) for repeat grants, granted-by, reason. Searchable client-side + year filter + CSV export.
   - **Of-The-Year winners** (`/api/reports/of-the-year`): year/category sorted, with human-readable `category_label` ("Chapter of the Year", "Member of the Year", etc.) — driven by a local `_OTY_LABELS` dict mirrored from `routes/of_the_year.CATEGORY_LABELS`. Year filter + CSV export.
3. **Member Card photo cropping** — `Directory.jsx` grid card photos used `object-cover` (crops tall portraits at the top/bottom). Switched to `object-contain` inside the `aspect-[4/3]` frame so the entire uploaded picture is visible; letterboxing falls into the muted background. The 80×80 round detail-modal avatar (`<Avatar>`) is intentionally left as cover — it's a thumbnail identifier, not a card.

**Verification (iter48)**: testing_agent iteration_48.json — 11/11 backend pytest + 9/9 frontend Playwright PASS. No regressions. The legend on the dashboard now shows `Honorary Member`, `Regular Member`, `Silver Life Member` (real tier names from db.tiers). Awards report renders Riley Chen's 3 Life Membership Ribbon grants with ordinal pills.



### Phase AQ — Iteration 47: Member-facing Email preferences (2026-06-18)
Members can now self-manage which AOP emails they receive from Profile → Notifications without needing the email footer link:

1. **Backend** — new `GET / PUT /api/me/email-preferences`. Storage: `users.email_prefs = {blasts: bool, dues_reminders: bool}` (default both true). `email_opt_out` remains the master kill switch. `public_user()` now exposes both fields on `/api/auth/me`.
2. **Implicit re-subscribe** — when a member toggles any category back on via PUT (without explicitly passing `email_opt_out`), the master `email_opt_out` flag is auto-cleared. Saves them clicking the public re-subscribe button.
3. **Per-category filters** — `resolve_segment()` now also excludes `email_prefs.blasts === false`; dues-reminder cron now also excludes `email_prefs.dues_reminders === false`.
4. **Frontend** — `EmailPreferences` card added to Profile → Notifications tab with three switches (`email-prefs-blasts-toggle`, `email-prefs-dues-toggle`, `email-prefs-optout-toggle`), per-category descriptions, an amber `email-prefs-master-banner` shown when master kill is on, and a Save button that toasts on success. Category toggles visually disable when master is on (`checked={cat && !optOut}`) but underlying state is preserved.

**Verification (iter47)**: testing_agent iteration_47.json — 12/12 backend pytest + 7/7 frontend Playwright PASS, including implicit-re-subscribe and persistence-after-navigation. No bugs found.



### Phase AP — Iteration 46: Email deliverability + one-click unsubscribe (2026-06-18)
User reported admin email blasts landing in production members' junk folders. Verified the org is sending from their own domain (`info@aop-app.org`), not the Resend sandbox — so the fix is bulk-sender hygiene + DNS authentication, not domain switching. Shipped:

1. **`send_bulk_email()` helper** (`server.py`) — every blast and dues reminder now goes through this wrapper which auto-attaches:
   - Multipart: HTML + auto-derived plain-text fallback (HTML-only is a strong spam signal)
   - `Reply-To: info@aop-app.org`
   - `List-Unsubscribe: <https://.../api/email/unsubscribe?token=...>, <mailto:info@aop-app.org?subject=unsubscribe>`
   - `List-Unsubscribe-Post: List-Unsubscribe=One-Click` (RFC 8058 — required by Gmail/Yahoo for senders >5000/day, used as positive signal even below that threshold)
   - `Precedence: bulk` header
   - Visible footer with organization mailing address + Unsubscribe link (CAN-SPAM)
2. **Opt-out infrastructure**:
   - `users.email_opt_out` boolean + `email_opt_out_at` timestamp
   - `resolve_segment()` excludes opted-out members from blasts (except `test_only`)
   - Dues-reminder cron also skips `email_opt_out=true`
3. **Public endpoints** (no auth, HMAC-token-secured):
   - `GET / POST /api/email/unsubscribe?token=...` → flips opt_out, 302s to `/unsubscribed?status=ok|invalid`
   - `POST /api/email/resubscribe?token=...` → flips opt_out back
   - `GET /api/email/unsubscribe-status?token=...` → read state for /unsubscribed page
4. **`GET /api/email/deliverability`** (admin) — returns sender, reply-to, sending domain, opt-out count, sandbox warning flag, and a DNS checklist (SPF / DKIM / DMARC / feedback-loop) with the org's real domain interpolated into the DMARC value.
5. **Public `/unsubscribed` React page** (`Unsubscribed.jsx`) — confirms the opt-out, shows email, offers "I clicked by mistake — re-subscribe" button.
6. **Admin → Email → Deliverability tab** with sender/reply-to/sending-domain tiles, opt-out counter, DNS checklist, mail-tester.com link, and a green summary card listing all the headers/footers the app already attaches.

**Production note**: The unsubscribe link's host is built from backend env `FRONTEND_URL`. Preview env currently has it set to the preview URL — when deployed to prod, this must be `FRONTEND_URL=https://aop-app.org` in the production backend env (otherwise members clicking Unsubscribe in production emails would land on the preview env). New env vars introduced (with safe defaults): `RESEND_REPLY_TO`, `ORG_MAILING_ADDRESS`, `UNSUBSCRIBE_SECRET` (falls back to `JWT_SECRET`).

**Verification (iter46)**: testing_agent iteration_46.json — 10/10 backend pytest + 8/8 frontend Playwright PASS. Unsubscribe token format: `base64url(user_id + '.' + first16(b64url(HMAC-SHA256(SECRET, user_id))))`.



### Phase AO — Iteration 45: CSV import dry-run preview (2026-06-18)
Two-step admin CSV import flow on `/hours`:

1. **Backend** — `POST /api/hours/admin/csv` now accepts a `dry_run` query param. When `dry_run=true`, the endpoint validates the file exactly as it would for a real import, builds a per-row `preview` list (each row tagged `status: "ready" | "error"` with resolved `member_name`, `email`, parsed `hours`, `date`, `activity` and an error `message` when applicable), and returns `{dry_run, created: 0, ready, failed, total, errors, preview, preview_truncated}` **without writing anything**. Preview list is capped at 200 entries; `preview_truncated` flag signals overflow.
2. **Frontend** — `CsvImportDialog` is now a wizard: picking the file auto-POSTs to `?dry_run=true` and renders a sticky-header table (`hours-csv-preview-table`) with READY/ERROR pills, member name, hours, date, activity (or red error message). The header chip summarises `✅ X ready · ⚠ Y errors of N rows`. A "Confirm import (X rows)" CTA POSTs without `dry_run` to actually persist. "Choose different file" resets to the picker; after a successful confirm "Import another file" cycles back. Confirm is disabled when `ready === 0`.

**Verification (iter45)**: testing_agent iteration_45.json — 6/6 new pytest cases pass (dry-run skips insert, confirm writes, errors-only dry-run, preview cap > 200, authz), 15/15 iter42 regression still green, 10/10 frontend Playwright checks pass (auto-preview on file select, READY/ERROR rendering, dynamic confirm label, disabled confirm when ready=0, both reset paths).



### Phase AN — Iteration 44: Admin bulk hours + CSV import (2026-06-18)
Two new admin productivity tools for volunteer-hours logging:

1. **Multi-member hours** — `Hours.jsx` `LogHoursDialog` for admins replaces the single-member Select with a searchable checkbox list (data-testid `hours-admin-member-search` + `hours-admin-member-checkbox-{id}`). Selecting 2+ members routes the save to a new `POST /api/hours/admin/bulk` endpoint that auto-approves the same hours/activity for every selected member in one round-trip; selecting exactly 1 keeps the original `/hours/admin` path. Submit button label switches dynamically ("Log hours for N members (auto-approved)").
2. **CSV import** — New "Import CSV" button beside "Log hours" opens `CsvImportDialog`. Required columns: `member_email, hours, date`; optional: `activity, event_type, agency_name, host_*`. Tolerates UTF-8 BOM, MM/DD/YYYY dates, and reports per-row errors. Endpoints added:
   - `POST /api/hours/admin/csv` (multipart, max 1000 rows / 1 MB, auto-approve, returns `{created, failed, total, errors[]}`)
   - `GET /api/hours/admin/csv/template` (sample CSV download)
3. **Serializer audit fields** — `hours_out()` now surfaces `logged_by_admin`, `approved_by`, `approved_by_name`, `approved_at`, `imported_from_csv`, `csv_row` so UIs/audits can distinguish admin-logged vs self-logged vs CSV-imported rows.

**Verification (iter44)**: testing_agent iteration_42.json — 15/15 pytest cases pass (bulk validation, de-dupe, mixed valid/invalid ids, CSV happy path, CSV bad columns/dates/hours, authz). Frontend 13/13 Playwright checks pass (multi-select counter, single-vs-bulk endpoint routing, CSV upload success + error panels, member-side hidden controls). Testing agent fixed a missing `@api.get("/hours")` decorator regression during this iteration.



### Phase AM — Iteration 43: Sub-events in parent-create + edit/delete from EventDetail (2026-06-17)
Two related admin UX upgrades for events with sub-events (anniversary / retreat / weekend umbrellas):

1. **Draft sub-events during parent creation** — `Admin.jsx` `EventDialog` now renders a new "Sub-events under this event" section (data-testid `event-subevents-section`) when creating a brand-new event. Admins click `add-subevent-draft-btn` to append draft rows (title, category, starts/ends, location, allows_ticket_types). On Save, the parent is POSTed first, then each draft is POSTed sequentially with `parent_event_id` set to the new parent id. The section is gated to `{!event && (...)}` so editing an existing event hides it.
2. **Edit / Delete sub-events from EventDetail** — Refactored `SubEventCreateForm` in `EventDetail.jsx` into a reusable `SubEventForm` that handles both create and edit. New `SubEventCard` wraps each sub-event with admin-only `sub-event-edit-{id}` and `sub-event-delete-{id}` buttons. Edit opens a Dialog pre-filled with the sub-event data and PUTs `/api/events/{sub_id}`. Delete confirms and DELETEs the sub-event.

**Verification (iter43)**: testing_agent iteration_41.json — 7/7 frontend scenarios PASS (drafts POST sequentially with correct parent_event_id, remove button discards before save, edit dialog is pre-filled and PUTs successfully, delete removes the card, non-admin members do not see edit/delete buttons).



### Phase AK — Iteration 42: Dues reminders polish (2026-06-06)
Three follow-ups on the iter41 dues-reminders work:

1. **Removed navbar "10 Year Anniversary" badge** — the pill in `Navbar.jsx` (data-testid `nav-anniversary-badge`) was overlapping the "Phi" in the logo on home page. The badge has been deleted; the anniversary page is still reachable via the Home hero CTA and direct `/anniversary` URL.

2. **NEW: Admin → Reports → "Dues reminders" tab** showing the audit log of every dues-reminder email sent. Features:
   - 4 stat tiles (one per stage) showing all-time + last-30-day counts
   - Filters: stage, sent-on-or-after, sent-on-or-before
   - Columns: sent timestamp, stage chip, member, email, cycle expiration, "Paid since" badge (when `current_expires_at > row.expires_at`), current status
   - CSV export
   - Backend: `GET /api/reports/dues-reminders` + `GET /api/reports/dues-reminders/summary` in `routes/reports.py`. The detail endpoint enriches each row with current member status so admins can see who paid after the email went out vs. who still hasn't.

3. **Per-stage email templates now admin-editable** — moved out of code into the campaign document:
   - New `stage_templates: { stage_id: {subject, body_html} }` field on `automated_emails` docs
   - `DUES_REMINDER_DEFAULT_TEMPLATES` in `server.py` is the fallback when no override exists
   - `_apply_dues_placeholders()` supports `{{first_name}} {{member_name}} {{expires_at}} {{grace_days}} {{reactivation_fee}} {{pay_link}} {{contact_email}}`
   - New `GET /api/automated-emails/dues-reminder-defaults` returns stages + defaults + placeholder list for the frontend
   - Frontend `AutomatedEmailsAdmin.jsx` renders 4 stage editor cards (subject input + body textarea + "Customized" pill + Reset-to-default button) inside the dues campaign dialog
   - PUT `/automated-emails/{id}` honors `stage_templates` for dues_reminders kind (still ignores name/subject/body/audience/sections for system-managed campaigns)

**Verification (iter42)**
- Live API smoke: `/api/automated-emails/dues-reminder-defaults` returns 4 stages + 7 placeholders + 4 default templates. `/api/reports/dues-reminders` returns rows + per-stage summary. Admin login flow → Reports → Dues reminders tab renders with 4 stat tiles + filter row + empty-state table. Edit "Annual Dues Reminders" → 4 stage editor cards render with subject/body fields pre-filled from defaults.
- Programmatic test: admin override `{subject: "CUSTOM SUBJ for {{first_name}}", body_html: "<p>CUSTOM BODY exp={{expires_at}}</p>"}` is correctly rendered with placeholders substituted; baked defaults still used when no override present; dedupe + paid-cycle reset unchanged.

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
