# ClubHaven — Product Requirements Document

## Problem Statement
Build an app that mirrors Club Express. User wants the same capabilities — a full club management platform covering membership, events, and communications.

## V1 Scope (agreed with user)
- Member management: directory, profiles, join/renewal
- Events & RSVPs: calendar + list, registration/ticketing
- Website CMS: pages + news/blog
- JWT-based email/password auth
- AI event description writer + email drafting (Claude Sonnet 4.5 via Emergent LLM key)
- Skip Stripe payments for V1
- Vibrant/community design (Outfit + Work Sans, warm coral/yellow/sage palette)

## User Personas
1. **Club Admin** — creates events, writes news, manages pages, uses AI drafting.
2. **Member** — RSVPs to events, maintains profile, renews membership, browses directory.
3. **Visitor** — reads news, sees upcoming events, joins the club.

## Architecture
- **Backend**: FastAPI + Motor (async MongoDB) + PyJWT + bcrypt + emergentintegrations
- **Frontend**: React 19 + React Router + Tailwind + shadcn/ui + sonner toasts + date-fns
- **Auth**: httpOnly cookies (access 24h, refresh 7d), SameSite=None+Secure for HTTPS preview
- **AI**: emergentintegrations LlmChat → anthropic/claude-sonnet-4-5-20250929

## Implemented (2026-02)
- Backend: all routes under /api (auth, members, events, news, pages, AI)
- Admin-only guards via `require_admin` dependency
- Idempotent admin + demo seed (admin + 5 members + 3 events + 2 news articles + about/contact pages)
- Brute-force lockout keyed on X-Forwarded-For + email (5 fails / 15 min)
- MongoDB indexes: users.email unique, events.id unique, rsvps compound unique, pages.slug unique
- Frontend: Home, Events (list + mini calendar), Event detail with RSVP, News list + detail, Directory with search, Profile (edit + renewal + my events), CMS pages, Login/Register, Admin console (events/news/pages/members tabs) with inline Claude AI writer
- Warm glassy navbar, coral/yellow/sage theme, Outfit + Work Sans fonts, rounded-2xl cards

## Test Status (iteration_1)
- Backend: 22/23 passing. Brute-force fix applied post-test (X-Forwarded-For).

## Backlog

### P0 (should do next if user wants polish)
- [ ] Admin member role toggle + delete member
- [ ] Event categories + filter chips on /events
- [ ] Email verification flow (token in Mongo, reset-password UI)

### P1
- [ ] Stripe integration for paid events + dues (test key available in env)
- [ ] Discussion forums (threads + comments)
- [ ] Email blasts (member list + send via Resend)
- [ ] Documents library (file uploads to object storage)
- [ ] Committees / Groups module

### P2
- [ ] Recurring events
- [ ] Event waitlist when capacity filled
- [ ] Member birthdays + anniversaries widget
- [ ] iCal feed for events
- [ ] Public signup approval workflow
- [ ] Custom domain + branding
- [ ] Mobile app wrapper

## Credentials
See `/app/memory/test_credentials.md`.
