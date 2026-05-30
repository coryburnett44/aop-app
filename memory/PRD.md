# CORY BURNETT / Overflow Investment Legacy — Invoice & Payments

## Original Problem Statement
> Build an invoice page where I can invoice businesses or people to have them click on a link and pay. Have the money go straight to my bank account. Make the Invoice title "Cory Burnett" in ALL CAPS and font bigger than all the font on the page, and have "or Overflow Investment Legacy" on the bottom of the title in regular size font. Allow me to make the invoice detailed.

## User Choices
- Payment integration: **PayPal** (sandbox mode for now)
- Invoice detail level: **Full** — items, tax, discount, terms, due date, customer info
- Management: **Dashboard** (view/manage all invoices)
- Design: **Professional/Corporate** (Swiss & High-Contrast archetype, light theme)
- Currency: **USD**

## Architecture
- **Backend**: FastAPI (`/app/backend/server.py`), MongoDB via Motor, PayPal REST API via httpx
- **Frontend**: React + React Router + Tailwind + shadcn/ui, `@paypal/react-paypal-js`, sonner toasts
- **Routes**:
  - `/` Dashboard (list, stats, copy pay link)
  - `/invoices/new` Create form
  - `/invoices/:id/edit` Edit form
  - `/pay/:id` **Public pay page** with PayPal button (shareable)
- **API endpoints (all `/api` prefixed)**:
  - `GET /config/paypal`
  - `POST/GET /invoices`, `GET/PATCH/DELETE /invoices/{id}`
  - `POST /invoices/{id}/paypal/create-order` and `POST /invoices/{id}/paypal/capture/{order_id}`
  - `POST /invoices/{id}/mark-paid`

## Completed (2026-02-XX, iteration 1)
- [x] Bold "CORY BURNETT" header (Chivo, all-caps, largest font) with "or Overflow Investment Legacy" subtitle on dashboard and pay page
- [x] Invoice CRUD with line items, tax %, discount $, notes, terms, due/issue dates
- [x] Auto-computed subtotal / tax / total
- [x] Public shareable pay page at `/pay/:id`
- [x] PayPal Checkout flow (create-order + capture) — gracefully shows "Not configured" warning until live keys are added
- [x] Dashboard stats (total/paid/outstanding) + copy pay link, edit, delete
- [x] Status badges (draft/sent/paid/overdue) + printable invoice
- [x] 14 backend tests + Playwright e2e — all passed (100% / 100%)

## Backlog
### P0 (to unlock real payments)
- Add real PayPal sandbox / live `PAYPAL_CLIENT_ID` + `PAYPAL_SECRET` to `backend/.env` and `REACT_APP_PAYPAL_CLIENT_ID` to `frontend/.env`; restart backend
- PayPal webhook endpoint to handle async events (refunds, disputes)

### P1
- Validate captured PayPal order_id matches stored `paypal_order_id` before marking paid (security)
- Email invoice to customer (Resend or SendGrid)
- PDF export of invoice
- Authentication (only the owner can create/edit; pay page stays public)
- Unique index on `invoice_number`

### P2
- Recurring invoices
- Multi-currency
- Partial payments / deposits
- Late-fee automation
- Stripe as alternate payment rail
