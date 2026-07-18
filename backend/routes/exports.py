"""Iter 127 — CSV + PDF exports for admin views.

Endpoints:
  GET  /admin/members/export.csv     — full member directory CSV with
                                       every personal field + awards +
                                       events + rsvps + hours + dues.
  GET  /reports/{kind}/export.pdf    — landscape PDF snapshot of the
                                       matching /reports endpoint.
                                       kind ∈ {members, rsvps, hours,
                                       donations, event-tickets, awards,
                                       dues, dues-reminders, recruitment}
                                       (the ones with tabular payloads).

Every export respects the same admin-scope rules the JSON endpoints use
via the injected `admin_tab_dep("reports")` and `is_chapter_scoped`.
"""
from __future__ import annotations

import csv
import io
import threading
from typing import Optional

from fastapi import Depends, HTTPException, Response
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter, landscape
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import (
    SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, PageBreak, Image,
)


# Iter 130 — cover-letter header. AOP logo used across every export PDF so
# printed reports look on-brand. Fetched once per process on first PDF and
# cached in-memory.
AOP_LOGO_URL = "https://customer-assets.emergentagent.com/job_club-express-lite/artifacts/k67x4iui_Trendsetters%20logo.png"
AOP_ORG_NAME = "Alpha Omega Phi Military Fraternity & Sorority, Inc."
_LOGO_CACHE: dict = {"bytes": None, "err": False}
_LOGO_LOCK = threading.Lock()


def _load_logo_bytes() -> Optional[bytes]:
    """Fetch and cache the AOP logo. Returns None if the fetch fails —
    PDFs still render, just without the image."""
    if _LOGO_CACHE["bytes"] is not None or _LOGO_CACHE["err"]:
        return _LOGO_CACHE["bytes"]
    with _LOGO_LOCK:
        if _LOGO_CACHE["bytes"] is not None or _LOGO_CACHE["err"]:
            return _LOGO_CACHE["bytes"]
        try:
            import urllib.request
            with urllib.request.urlopen(AOP_LOGO_URL, timeout=8) as resp:
                _LOGO_CACHE["bytes"] = resp.read()
        except Exception:
            _LOGO_CACHE["err"] = True
    return _LOGO_CACHE["bytes"]


def register(
    api,
    *,
    db,
    admin_tab_dep,
    public_user,
    is_chapter_scoped,
    chapter_scope_user_ids,
    iso,
    now_utc,
    logger,
):
    # =====================================================================
    # Helpers
    # =====================================================================
    def _csv_response(rows, columns, filename):
        buf = io.StringIO()
        writer = csv.DictWriter(buf, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        for r in rows:
            # Coerce lists/dicts to human-readable strings so Excel doesn't choke.
            clean = {}
            for c in columns:
                v = r.get(c)
                if v is None:
                    clean[c] = ""
                elif isinstance(v, (list, tuple)):
                    clean[c] = "; ".join(str(x) for x in v)
                elif isinstance(v, dict):
                    clean[c] = "; ".join(f"{k}={vv}" for k, vv in v.items())
                elif isinstance(v, bool):
                    clean[c] = "Yes" if v else "No"
                else:
                    clean[c] = str(v)
            writer.writerow(clean)
        return Response(
            content=buf.getvalue(),
            media_type="text/csv",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    def _cover_header(title: str, subtitle: str, h1_style, h2_style) -> list:
        """Iter 130 — every export PDF starts with a common cover header:
        AOP logo + org name banner on the left, title + generated-at line
        on the right. Falls back to text-only if the logo fetch failed."""
        logo_bytes = _load_logo_bytes()
        # Right column: title + org name + subtitle.
        org_style = ParagraphStyle("org", parent=h2_style, fontSize=9, textColor=colors.HexColor("#0A2463"), spaceAfter=1, fontName="Helvetica-Bold")
        gen_style = ParagraphStyle("gen", parent=h2_style, fontSize=8, textColor=colors.grey, spaceAfter=2)
        stamp = f"Generated {iso(now_utc())[:19].replace('T', ' ')} UTC"
        right_flows = [
            Paragraph(AOP_ORG_NAME, org_style),
            Paragraph(title, h1_style),
            Paragraph(subtitle, h2_style),
            Paragraph(stamp, gen_style),
        ]
        if logo_bytes:
            try:
                img = Image(io.BytesIO(logo_bytes), width=0.75 * inch, height=0.75 * inch, kind="proportional")
                header_tbl = Table([[img, right_flows]], colWidths=[0.9 * inch, None])
                header_tbl.setStyle(TableStyle([
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 0),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                    ("LINEBELOW", (0, 0), (-1, -1), 0.75, colors.HexColor("#C8102E")),
                ]))
                return [header_tbl, Spacer(1, 8)]
            except Exception:
                pass
        # Fallback: text-only cover.
        return right_flows + [Spacer(1, 6)]
    def _pdf_response(title: str, columns: list, rows: list, filename: str, subtitle: str = "", col_weights: Optional[list] = None):
        """Renders a landscape PDF with a title, an optional subtitle,
        and a table of the given columns/rows. Long text cells wrap via
        the paragraph flowable so extended reasons/notes stay readable.

        `col_weights` (optional, same length as `columns`) sets the relative
        column widths so wider text columns (Name, Event, etc.) don't clip.
        Weights are normalized — e.g. [2, 1, 1] gives the first column 50%
        of the page width and the others 25% each. Defaults to equal widths.
        """
        buf = io.BytesIO()
        doc = SimpleDocTemplate(
            buf,
            pagesize=landscape(letter),
            leftMargin=0.4 * inch, rightMargin=0.4 * inch,
            topMargin=0.4 * inch, bottomMargin=0.4 * inch,
            title=title,
        )
        styles = getSampleStyleSheet()
        h1 = ParagraphStyle("h1", parent=styles["Heading1"], fontSize=16, spaceAfter=4, textColor=colors.HexColor("#0A2463"))
        h2 = ParagraphStyle("h2", parent=styles["Normal"], fontSize=9, textColor=colors.grey, spaceAfter=8)
        cell = ParagraphStyle("cell", parent=styles["Normal"], fontSize=8, leading=10, wordWrap="CJK")
        # Header cells use white text so the labels stay readable on the navy fill.
        header_cell = ParagraphStyle("header_cell", parent=cell, textColor=colors.white, fontName="Helvetica-Bold")
        story = _cover_header(title, subtitle or f"Generated {iso(now_utc())} · {len(rows)} rows", h1, h2)
        if not rows:
            story.append(Paragraph("<i>No data for the selected filters.</i>", cell))
        else:
            # Build table data — header row + one row per record. Wrap
            # every cell in Paragraph so long text doesn't clip.
            header = [Paragraph(c, header_cell) for c in columns]
            data = [header]
            for r in rows:
                data.append([Paragraph(_fmt_cell(r.get(c)), cell) for c in columns])
            # Compute column widths from weights.
            page_w = landscape(letter)[0] - 0.8 * inch
            weights = col_weights if col_weights and len(col_weights) == len(columns) else [1] * len(columns)
            total = float(sum(weights)) or float(len(columns))
            col_w = [page_w * (w / total) for w in weights]
            table = Table(data, colWidths=col_w, repeatRows=1)
            table.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0A2463")),
                ("TEXTCOLOR",  (0, 0), (-1, 0), colors.white),
                ("FONTNAME",   (0, 0), (-1, 0), "Helvetica-Bold"),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1),
                    [colors.white, colors.HexColor("#F5F6FA")]),
                ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#BEBEBE")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 4),
                ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ]))
            story.append(table)
        doc.build(story)
        pdf_bytes = buf.getvalue()
        buf.close()
        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    # Iter 131 — column set for the "rows" (landscape one-line-per-member)
    # layout. Two-letter-abbreviated headers keep the row compact enough that
    # every field still fits in a single landscape page. Weights sum to a
    # sensible visual balance across the full page width.
    _MEMBERS_ROW_COLUMNS = [
        ("Name",       "name",                    2.0),
        ("Email",      "email",                   2.4),
        ("Phone",      "phone",                   1.3),
        ("Address",    "address",                 2.2),
        ("City",       "city",                    1.1),
        ("ST",         "state",                   0.5),
        ("Zip",        "postal_code",             0.7),
        ("DOB",        "birth_date",              0.9),
        ("Chapter",    "chapter",                 1.2),
        ("Tier",       "tier",                    1.0),
        ("Role",       "role",                    0.9),
        ("Status",     "status",                  0.8),
        ("Joined",     "join_date",               0.9),
        ("Expires",    "membership_expires_at",   0.9),
        ("Bal",        "outstanding_balance_total", 0.6),
        ("Hrs",        "hours_approved_total",    0.5),
        ("Donations",  "donations_total",         0.8),
        ("Awards",     "awards",                  2.0),
    ]

    def _pdf_members_rows_response(title: str, subtitle: str, rows: list, filename: str, cols_meta: Optional[list] = None):
        """Iter 131 — landscape one-row-per-member view. Meant for printing
        rosters as flat sheets instead of one-card-per-member. Reuses
        `_pdf_response` so we get the branded cover header, navy/white
        column header row, and proportional column widths automatically."""
        cols = cols_meta if cols_meta else _MEMBERS_ROW_COLUMNS
        column_labels = [c[0] for c in cols]
        col_weights = [c[2] if len(c) >= 3 else 1.0 for c in cols]

        # Convert each row into a label-keyed dict so `_pdf_response` can
        # look it up directly. Flatten list-valued fields (awards / events
        # / rsvps) into compact bullet-separated strings so they still fit
        # in a single row.
        keyed = []
        for r in rows:
            kd = {}
            for (label, key, *_rest) in cols:
                v = r.get(key)
                if isinstance(v, list):
                    v = " · ".join(str(x) for x in v[:4])
                    if len(r.get(key) or []) > 4:
                        v += f" (+{len(r.get(key)) - 4} more)"
                kd[label] = v
            keyed.append(kd)

        return _pdf_response(
            title=title,
            columns=column_labels,
            rows=keyed,
            filename=filename,
            subtitle=subtitle or f"{len(rows)} members",
            col_weights=col_weights,
        )

    def _pdf_member_cards_response(title: str, subtitle: str, rows: list, filename: str):
        """Renders one detail card per member — every field from the CSV,
        grouped into readable sections (Personal · Membership · Awards ·
        Events · RSVPs · Hours & Donations · Preferences). Portrait letter
        page so column names never wrap or clip."""
        buf = io.BytesIO()
        doc = SimpleDocTemplate(
            buf,
            pagesize=letter,
            leftMargin=0.5 * inch, rightMargin=0.5 * inch,
            topMargin=0.5 * inch, bottomMargin=0.5 * inch,
            title=title,
        )
        styles = getSampleStyleSheet()
        h1 = ParagraphStyle("h1", parent=styles["Heading1"], fontSize=16, spaceAfter=4, textColor=colors.HexColor("#0A2463"))
        h2 = ParagraphStyle("h2", parent=styles["Normal"], fontSize=9, textColor=colors.grey, spaceAfter=10)
        name_hdr = ParagraphStyle("name_hdr", parent=styles["Heading2"], fontSize=13, spaceAfter=2, textColor=colors.HexColor("#0A2463"))
        section_hdr = ParagraphStyle("section_hdr", parent=styles["Normal"], fontSize=8, textColor=colors.white, backColor=colors.HexColor("#0A2463"), leftIndent=4, rightIndent=4, spaceBefore=6, spaceAfter=3, leading=11, fontName="Helvetica-Bold")
        cell = ParagraphStyle("cell", parent=styles["Normal"], fontSize=8, leading=10, wordWrap="CJK")
        story = _cover_header(title, subtitle or f"{len(rows)} members", h1, h2)
        if not rows:
            story.append(Paragraph("<i>No members match the current filters.</i>", cell))
        else:
            for idx, r in enumerate(rows):
                # Header row for this member card.
                display_name = _fmt_cell(r.get("name") or "(no name)")
                chapter = _fmt_cell(r.get("chapter") or "—")
                tier = _fmt_cell(r.get("tier") or "—")
                status = _fmt_cell(r.get("status") or "—")
                story.append(Paragraph(
                    f"{idx + 1}. {display_name}  <font size='9' color='#666666'>· {chapter} · {tier} · {status}</font>",
                    name_hdr,
                ))

                def _section(label: str, pairs: list):
                    """Renders a labeled section as a compact 2-col key/value table."""
                    story.append(Paragraph(f" {label.upper()}", section_hdr))
                    data = []
                    for k, v in pairs:
                        data.append([
                            Paragraph(f"<b>{k}</b>", cell),
                            Paragraph(_fmt_cell(v) or "—", cell),
                        ])
                    if not data:
                        return
                    page_w = letter[0] - 1.0 * inch
                    tbl = Table(data, colWidths=[page_w * 0.28, page_w * 0.72])
                    tbl.setStyle(TableStyle([
                        ("VALIGN", (0, 0), (-1, -1), "TOP"),
                        ("LEFTPADDING", (0, 0), (-1, -1), 4),
                        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                        ("TOPPADDING", (0, 0), (-1, -1), 2),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
                        ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#F5F6FA")),
                    ]))
                    story.append(tbl)

                _section("Personal", [
                    ("Full name", r.get("name")),
                    ("Email", r.get("email")),
                    ("Phone", r.get("phone")),
                    ("Gender", r.get("gender")),
                    ("Birth date", r.get("birth_date")),
                    ("Marital status", r.get("marital_status")),
                    ("Address", r.get("address")),
                    ("City", r.get("city")),
                    ("State", r.get("state")),
                    ("ZIP", r.get("postal_code")),
                    ("Country", r.get("country")),
                    ("Branch of service", r.get("branch_of_service")),
                    ("Line name", r.get("line_name")),
                    ("Intake line", r.get("intake_line")),
                ])
                _section("Membership", [
                    ("Chapter", r.get("chapter")),
                    ("Tier", r.get("tier")),
                    ("Role", r.get("role")),
                    ("Admin role", r.get("admin_role")),
                    ("Status", r.get("status")),
                    ("Lifetime?", r.get("is_lifetime_member")),
                    ("Join date", r.get("join_date")),
                    ("Created", r.get("created_at")),
                    ("Membership started", r.get("membership_started_at")),
                    ("Membership expires", r.get("membership_expires_at")),
                    ("Outstanding balance", f"${float(r.get('outstanding_balance_total') or 0):,.2f}"),
                    ("Total paid", f"${float(r.get('total_paid') or 0):,.2f}"),
                ])
                # Iter 132 — surface the actual line items so admins can see
                # WHAT the outstanding balance is made up of.
                if r.get("balance_lines"):
                    _section("Balance line items", [(f"{i + 1}.", line) for i, line in enumerate(r.get("balance_lines") or [])])
                _section("Awards", [("Awards granted", r.get("awards") or "—")])
                _section("Events attended", [("Check-ins", r.get("events_attended") or "—")])
                _section("RSVPs", [("Event RSVPs", r.get("rsvps") or "—")])
                _section("Hours & Donations", [
                    ("Hours approved", r.get("hours_approved_total")),
                    ("Hours pending", r.get("hours_pending_total")),
                    ("Donations total", r.get("donations_total")),
                    ("Recruits", r.get("recruits_count")),
                ])
                _section("Preferences", [
                    ("Email opt-out", r.get("email_opt_out")),
                    ("SMS opt-out", r.get("sms_opt_out")),
                    ("Member id", r.get("id")),
                ])
                # Page break between members so each card is self-contained.
                if idx < len(rows) - 1:
                    story.append(PageBreak())
        doc.build(story)
        pdf_bytes = buf.getvalue()
        buf.close()
        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )


    def _fmt_cell(v) -> str:
        if v is None: return ""
        if isinstance(v, bool): return "Yes" if v else "No"
        if isinstance(v, (list, tuple)): return "<br/>".join(str(x) for x in v)
        if isinstance(v, dict): return "<br/>".join(f"{k}={vv}" for k, vv in v.items())
        s = str(v)
        # ReportLab paragraphs need HTML entities escaped.
        return (s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))

    # =====================================================================
    # 1) Members full-fat CSV — every personal field for the admin.
    # =====================================================================
    _CSV_COLUMNS = [
        "id", "name", "email", "phone", "gender", "birth_date",
        "address", "city", "state", "postal_code", "country",
        "branch_of_service", "line_name", "intake_line", "marital_status",
        "chapter", "tier", "role", "admin_role",
        "status", "is_lifetime_member", "join_date", "created_at",
        "membership_started_at", "membership_expires_at",
        "outstanding_balance_total", "total_paid", "balance_lines",
        "hours_approved_total", "hours_pending_total",
        "donations_total", "recruits_count",
        "awards", "events_attended", "rsvps",
        "email_opt_out", "sms_opt_out", "bio",
    ]

    @api.get("/admin/members/export.csv")
    async def export_members_csv(
        admin: dict = Depends(admin_tab_dep("members")),
    ):
        """Full-fat member directory export. Includes personally-identifying
        information — restrict access via the members admin tab dep."""
        rows = await _build_full_member_rows(admin)
        fname = f"aop-members-{iso(now_utc())[:10]}.csv"
        return _csv_response(rows, _CSV_COLUMNS, fname)

    @api.get("/admin/members/export.pdf")
    async def export_members_pdf(
        # Iter 131 — `layout` chooses the visual shape:
        #   • `cards` (default) — portrait, one detail card per member
        #   • `rows`            — landscape one-line-per-member table
        layout: str = "cards",
        admin: dict = Depends(admin_tab_dep("members")),
    ):
        """Full-fat member directory PDF. Matches the CSV export field-for-field
        but renders each member as their own detail card (default) or as a
        landscape row-per-member roster (`?layout=rows`, useful for printing)."""
        rows = await _build_full_member_rows(admin)
        fname = f"aop-members-{iso(now_utc())[:10]}.pdf"
        layout = (layout or "cards").lower().strip()
        if layout == "rows":
            return _pdf_members_rows_response(
                title="AOP · Member Directory (roster)",
                subtitle=f"{len(rows)} members",
                rows=rows,
                filename=fname.replace(".pdf", "-roster.pdf"),
            )
        subtitle = f"Full member directory · {len(rows)} members"
        return _pdf_member_cards_response(
            title="AOP Members — Full Directory",
            subtitle=subtitle,
            rows=rows,
            filename=fname,
        )

    async def _build_full_member_rows(admin: dict) -> list:
        """Shared row-builder used by both the CSV and PDF admin-members
        exports so they never drift apart."""
        q: dict = {}
        if is_chapter_scoped(admin):
            allowed = await chapter_scope_user_ids(admin)
            if allowed is not None:
                q["id"] = {"$in": list(allowed)}

        users_cursor = db.users.find(q, {"_id": 0, "password_hash": 0}).sort("name", 1)
        users = await users_cursor.to_list(5000)

        # Pull side tables in one go so we don't N+1 for big rosters.
        chapters = {c["id"]: c for c in await db.chapters.find({}, {"_id": 0}).to_list(500)}
        tiers = {t["id"]: t for t in await db.tiers.find({}, {"_id": 0}).to_list(200)}

        rows = []
        for u in users:
            uid = u["id"]
            # Awards for this member.
            grants = await db.award_grants.find(
                {"user_id": uid}, {"_id": 0, "award_name": 1, "granted_at": 1, "reason": 1, "auto_granted": 1}
            ).sort("granted_at", 1).to_list(200)
            awards_str = [
                f"{g.get('award_name','')} ({(g.get('granted_at') or '')[:10]})"
                + (" [auto]" if g.get("auto_granted") else "")
                for g in grants
            ]

            # Events attended (via checkins).
            cks = await db.checkins.find(
                {"user_id": uid}, {"_id": 0, "event_title": 1, "checked_in_at": 1}
            ).sort("checked_in_at", 1).to_list(500)
            events_attended = [f"{c.get('event_title','')} ({(c.get('checked_in_at') or '')[:10]})" for c in cks]

            # RSVPs (upcoming + past).
            rsvps_docs = await db.rsvps.find(
                {"user_id": uid}, {"_id": 0, "event_id": 1, "ticket_type": 1, "created_at": 1, "guests": 1}
            ).to_list(500)
            event_titles = {}
            if rsvps_docs:
                ev_ids = list({r.get("event_id") for r in rsvps_docs if r.get("event_id")})
                ev_docs = await db.events.find(
                    {"id": {"$in": ev_ids}}, {"_id": 0, "id": 1, "title": 1}
                ).to_list(len(ev_ids))
                event_titles = {e["id"]: e.get("title", "") for e in ev_docs}
            rsvps_str = []
            for r in rsvps_docs:
                title = event_titles.get(r.get("event_id"), r.get("event_id") or "")
                tt = r.get("ticket_type") or "general"
                guest_ct = len(r.get("guests") or [])
                extra = f" +{guest_ct}g" if guest_ct else ""
                rsvps_str.append(f"{title} [{tt}{extra}]")

            # Hours totals.
            hrs_agg = await db.volunteer_hours.aggregate([
                {"$match": {"user_id": uid}},
                {"$group": {"_id": "$status", "hrs": {"$sum": "$hours"}}},
            ]).to_list(10)
            hrs_by_status = {a["_id"]: float(a.get("hrs") or 0) for a in hrs_agg}

            # Donations total (approved transactions).
            don_agg = await db.transactions.aggregate([
                {"$match": {"user_id": uid, "type": "donation", "status": {"$in": ["approved", "paid"]}}},
                {"$group": {"_id": None, "amt": {"$sum": "$amount"}}},
            ]).to_list(1)
            donations_total = float((don_agg[0].get("amt") if don_agg else 0) or 0)

            # Recruits count.
            recruits_count = await db.users.count_documents({"recruiter_id": uid})

            # Iter 132 — address fields are FLAT on the user doc (city/state/
            # zip_code/country are all top-level). The `address` field itself
            # is a plain string. My earlier assumption that `address` was a
            # nested dict was wrong and caused city/state/DOB/etc. to export
            # as empty.
            addr_val = u.get("address")
            if isinstance(addr_val, dict):
                # Legacy safety net — some old docs may have stored nested.
                addr_line = addr_val.get("line1") or addr_val.get("street") or ""
                city = addr_val.get("city") or u.get("city", "") or ""
                state = addr_val.get("state") or u.get("state", "") or ""
                postal = addr_val.get("postal_code") or addr_val.get("zip") or addr_val.get("zip_code") or u.get("zip_code", "") or ""
                country = addr_val.get("country") or u.get("country", "") or ""
            else:
                addr_line = addr_val or ""
                city = u.get("city", "") or ""
                state = u.get("state", "") or ""
                postal = u.get("zip_code", "") or ""
                country = u.get("country", "") or ""

            # Iter 132 — outstanding balance is COMPUTED from `balance_lines`
            # per routes/balances.py (never stored). Reading a stored
            # `outstanding_balance_total` was returning 0 for every member.
            balance_lines = u.get("balance_lines") or []
            outstanding_total = round(
                sum(float(ln.get("amount", 0) or 0) for ln in balance_lines if not ln.get("paid_at")),
                2,
            )
            total_paid = round(
                sum(float(ln.get("amount", 0) or 0) for ln in balance_lines if ln.get("paid_at")),
                2,
            )
            # Also compact the balance lines themselves for a per-member detail
            # field the card layout can show.
            balance_lines_summary = [
                f"{ln.get('label','')} (${float(ln.get('amount',0) or 0):,.2f}"
                + (f" — paid {(ln.get('paid_at') or '')[:10]}" if ln.get("paid_at") else " — unpaid")
                + ")"
                for ln in balance_lines
            ]

            # Iter 132 — DOB is stored under `birthdate` (not `birth_date`).
            # Membership tier can also be stored as `membership_tier` string
            # when no explicit tier_id was set — fall back to that.
            chapter = chapters.get(u.get("chapter_id"))
            tier = tiers.get(u.get("tier_id"))
            tier_name = tier.get("name", "") if tier else (u.get("membership_tier", "") or "")

            # Compose a display name from first/middle/last if `name` is empty.
            display_name = u.get("name", "") or " ".join(
                x for x in [u.get("first_name", ""), u.get("middle_name", ""), u.get("last_name", "")]
                if x
            ).strip()

            rows.append({
                "id": uid,
                "name": display_name,
                "email": u.get("email", ""),
                "phone": u.get("phone", ""),
                "gender": u.get("gender", ""),
                "birth_date": (u.get("birthdate") or u.get("birth_date") or "")[:10],
                "address": addr_line,
                "city": city,
                "state": state,
                "postal_code": postal,
                "country": country,
                "chapter": chapter.get("name", "") if chapter else "",
                "tier": tier_name,
                "role": u.get("role", ""),
                "admin_role": u.get("admin_role", "") or "",
                "status": u.get("status", ""),
                "is_lifetime_member": bool(u.get("is_lifetime_member")),
                "join_date": (u.get("join_date") or "")[:10],
                "created_at": (u.get("created_at") or "")[:10],
                "membership_started_at": (u.get("membership_started_at") or "")[:10],
                "membership_expires_at": (u.get("membership_expires_at") or "")[:10],
                "outstanding_balance_total": outstanding_total,
                "total_paid": total_paid,
                "balance_lines": balance_lines_summary,
                "hours_approved_total": round(hrs_by_status.get("approved", 0), 2),
                "hours_pending_total": round(hrs_by_status.get("pending", 0), 2),
                "donations_total": round(donations_total, 2),
                "recruits_count": recruits_count,
                "awards": awards_str,
                "events_attended": events_attended,
                "rsvps": rsvps_str,
                # Extra profile fields the card layout can surface.
                "branch_of_service": u.get("branch_of_service", "") or "",
                "intake_line": u.get("intake_line", "") or "",
                "line_name": u.get("line_name", "") or "",
                "marital_status": u.get("marital_status", "") or "",
                "bio": u.get("bio", "") or "",
                "email_opt_out": bool(u.get("email_opt_out")),
                "sms_opt_out": bool(u.get("sms_opt_out")),
            })
        return rows

    # =====================================================================
    # 2) PDF exports — one per report kind. Delegates to the JSON handler
    # so a filter tweak on the report shows up in the PDF automatically.
    # Each column tuple is (label, key, weight). Weight controls the
    # proportional column width — Name/Member columns get 2x so long
    # names don't clip. Weights default to 1 if omitted.
    # =====================================================================
    _PDF_COLUMNS = {
        "members": [
            ("Name", "name", 2.2),
            ("Email", "email", 2.4),
            ("Phone", "phone", 1.4),
            ("Chapter", "chapter_name", 1.2),
            ("Tier", "tier_name", 1.0),
            ("Status", "status", 0.9),
            ("Joined", "join_date", 1.0),
            ("Expires", "membership_expires_at", 1.0),
        ],
        "rsvps": [
            ("Member", "user_name", 2.0),
            ("Chapter", "chapter_name", 1.2),
            ("Event", "event_title", 2.4),
            ("Ticket", "ticket_type", 1.0),
            ("Guests", "guest_count", 0.7),
            ("RSVP'd", "rsvped_at", 1.0),
            ("Event start", "event_start_at", 1.0),
        ],
        "hours": [
            ("Member", "user_name", 1.9),
            ("Chapter", "chapter_name", 1.1),
            ("Date", "date", 1.0),
            ("Hours", "hours", 0.7),
            ("Type", "event_type", 1.1),
            ("Agency", "agency_name", 1.2),
            ("Activity", "activity", 2.4),
            ("Status", "status", 0.9),
        ],
        "donations": [
            ("Member", "user_name", 2.0),
            ("Cause", "cause_name", 2.4),
            ("Amount", "amount", 0.9),
            ("Method", "method", 1.0),
            ("Status", "status", 0.9),
            ("Date", "created_at", 1.0),
        ],
        "recruitment": [
            ("Recruiter", "recruiter_name", 2.0),
            ("Recruit", "recruit_name", 2.0),
            ("Chapter", "chapter_name", 1.2),
            ("Date", "date_recruited", 1.0),
            ("Recruit email", "recruit_email", 2.0),
            ("Notes", "notes", 2.4),
        ],
        "awards": [
            ("Member", "user_name", 2.0),
            ("Award", "award_name", 2.4),
            ("Granted", "granted_at", 1.0),
            ("Granted by", "granted_by_name", 1.6),
            ("Reason", "reason", 2.6),
            ("Auto?", "auto_granted", 0.6),
        ],
        "event-tickets": [
            ("Member", "user_name", 2.0),
            ("Event", "event_title", 2.4),
            ("Ticket", "ticket_type", 1.0),
            ("Amount", "amount", 0.9),
            ("Status", "status", 1.0),
            ("Created", "created_at", 1.0),
        ],
        "dues": [
            ("Member", "user_name", 2.0),
            ("Amount", "amount", 0.9),
            ("Status", "status", 1.0),
            ("Method", "method", 1.0),
            ("Zeffy id", "zeffy_transaction_id", 1.8),
            ("Created", "created_at", 1.0),
            ("Approved", "approved_at", 1.0),
        ],
        "dues-reminders": [
            ("Member", "user_name", 2.0),
            ("Stage", "stage", 1.0),
            ("Sent at", "sent_at", 1.2),
            ("Channel", "channel", 1.0),
            ("Status", "status", 1.0),
            ("Renewal date", "renewal_date", 1.2),
        ],
    }

    def _rows_for_pdf(kind: str, docs: list) -> list:
        """Flatten each record's fields into a plain-dict row keyed by
        the column keys defined in _PDF_COLUMNS[kind]. Handles the
        camelCased shapes each /reports endpoint returns."""
        return _rows_for_pdf_with_cols(_PDF_COLUMNS[kind], kind, docs)

    def _rows_for_pdf_with_cols(cols: list, kind: str, docs: list) -> list:
        """Same as _rows_for_pdf but accepts an explicit column list — used
        when the admin trims the column set via the ?columns=… whitelist."""
        out = []
        for d in docs:
            row = {}
            for tup in cols:
                _label, key = tup[0], tup[1]
                v = d.get(key)
                # Common nested lookups per kind.
                if v is None and kind == "members":
                    if key == "chapter_name":
                        v = (d.get("chapter") or {}).get("name") if isinstance(d.get("chapter"), dict) else d.get("chapter_name")
                    elif key == "tier_name":
                        v = (d.get("tier") or {}).get("name") if isinstance(d.get("tier"), dict) else d.get("tier_name") or d.get("membership_tier")
                    elif key == "join_date":
                        v = d.get("join_date") or d.get("created_at")
                if v is None and kind == "rsvps" and key == "guest_count":
                    v = len(d.get("guests") or [])
                if v is None and kind == "awards" and key == "user_name":
                    v = d.get("current_user_name") or d.get("user_name")
                if isinstance(v, str) and len(v) > 10 and v.endswith("Z"):
                    v = v[:10]
                elif isinstance(v, str) and "T" in v and len(v) >= 10:
                    v = v[:10]
                row[key] = v
            out.append(row)
        return out

    async def _load_transactions_for_pdf(
        kind: str,
        admin: dict,
        year: Optional[int] = None,
        quarter: Optional[int] = None,
        month: Optional[int] = None,
        status: Optional[str] = None,
    ) -> list:
        """Reads db.transactions for the dues / event-ticket PDF exports.
        Not a delegate — the current UI reads /transactions with filters,
        so we mirror that here."""
        q: dict = {}
        if kind == "dues":
            q["purpose"] = "dues"
        elif kind == "event-tickets":
            q["type"] = "event_ticket"
        if status:
            q["status"] = status
        # Optional year/quarter/month bounding on created_at.
        if year:
            if month:
                start = f"{year}-{month:02d}-01"
                nxt_m = 1 if month == 12 else month + 1
                nxt_y = year + 1 if month == 12 else year
                end = f"{nxt_y}-{nxt_m:02d}-01"
            elif quarter:
                qm = {1: 1, 2: 4, 3: 7, 4: 10}[quarter]
                start = f"{year}-{qm:02d}-01"
                nxt = qm + 3
                nxt_y = year + (1 if nxt > 12 else 0)
                nxt_m = nxt - 12 if nxt > 12 else nxt
                end = f"{nxt_y}-{nxt_m:02d}-01"
            else:
                start = f"{year}-01-01"
                end = f"{year + 1}-01-01"
            q["created_at"] = {"$gte": start, "$lt": end}
        if is_chapter_scoped(admin):
            allowed = await chapter_scope_user_ids(admin)
            if allowed is not None:
                q["user_id"] = {"$in": list(allowed)}
        rows = await db.transactions.find(q, {"_id": 0}).sort("created_at", -1).limit(5000).to_list(5000)
        return rows

    @api.get("/reports/{kind}/columns")
    async def report_pdf_columns(kind: str, layout: str = "default", _: dict = Depends(admin_tab_dep("reports"))):
        """Iter 130 — enumerates available PDF columns for a given report
        kind so the frontend picker can render checkboxes with the right
        labels + default-on state.

        Iter 131 — for kind=members, `?layout=rows` returns the landscape
        roster columns instead of the full CSV field set (the card layout
        does not currently expose a column picker — every field always
        prints in its own section)."""
        k = (kind or "").lower().strip()
        if k not in _PDF_COLUMNS:
            raise HTTPException(status_code=400, detail=f"Unknown report kind {k!r}")
        if k == "members" and (layout or "").lower().strip() == "rows":
            source = _MEMBERS_ROW_COLUMNS
        else:
            source = _PDF_COLUMNS[k]
        return {
            "kind": k,
            "layout": (layout or "default").lower(),
            "columns": [
                {"key": c[1], "label": c[0], "default": True}
                for c in source
            ],
        }

    @api.get("/reports/{kind}/export.pdf")
    async def export_report_pdf(
        kind: str,
        # Passthrough query params — we forward whatever the report
        # endpoint understands via `request` in a moment.
        chapter_id: Optional[str] = None,
        tier_id: Optional[str] = None,
        role: Optional[str] = None,
        status_filter: Optional[str] = None,
        event_id: Optional[str] = None,
        parent_event_id: Optional[str] = None,
        ticket_type: Optional[str] = None,
        year: Optional[int] = None,
        quarter: Optional[int] = None,
        month: Optional[int] = None,
        date_field: Optional[str] = None,
        cause_id: Optional[str] = None,
        status: Optional[str] = None,
        recruiter_id: Optional[str] = None,
        award_id: Optional[str] = None,
        # Iter 130 — comma-separated whitelist of column keys the admin
        # wants included in the PDF (matches keys in _PDF_COLUMNS[kind]).
        # Unrecognized keys are ignored; empty means "include everything".
        columns: Optional[str] = None,
        # Iter 131 — the members PDF supports two layouts: `cards` (default,
        # portrait one-page-per-member) or `rows` (landscape roster).
        layout: str = "cards",
        admin: dict = Depends(admin_tab_dep("reports")),
    ):
        kind = (kind or "").lower().strip()
        if kind not in _PDF_COLUMNS:
            raise HTTPException(
                status_code=400,
                detail=f"Unknown report kind {kind!r}. Supported: {sorted(_PDF_COLUMNS)}",
            )
        # `members` PDF export uses the full-card layout so every field
        # from the CSV export shows up — no column clipping. Landscape
        # roster available via ?layout=rows for print-friendly output.
        if kind == "members":
            rows = await _build_full_member_rows(admin)
            subtitle = f"{len(rows)} members"
            if (layout or "cards").lower().strip() == "rows":
                # Honor the column whitelist against the row column set too.
                cols_meta = _MEMBERS_ROW_COLUMNS
                if columns:
                    wanted = {c.strip() for c in columns.split(",") if c.strip()}
                    filtered = [c for c in cols_meta if c[1] in wanted]
                    if filtered:
                        cols_meta = filtered
                return _pdf_members_rows_response(
                    title="AOP · Members Roster",
                    subtitle=subtitle,
                    rows=rows,
                    filename=f"aop-members-roster-{iso(now_utc())[:10]}.pdf",
                    cols_meta=cols_meta,
                )
            return _pdf_member_cards_response(
                title="AOP · Members Report",
                subtitle=subtitle,
                rows=rows,
                filename=f"aop-members-report-{iso(now_utc())[:10]}.pdf",
            )
        # `dues` and `event-tickets` don't have a dedicated /reports/* JSON
        # endpoint — they're derived views over `db.transactions`. We build
        # the rows inline.
        if kind in ("dues", "event-tickets"):
            docs = await _load_transactions_for_pdf(kind, admin, year=year, quarter=quarter, month=month, status=status)
        else:
            # Report kinds served by /reports/{kind} — but with a couple
            # of aliases (frontend `awards` → backend `award-grants`).
            target_kind = {"awards": "award-grants"}.get(kind, kind)
            # Look up the sibling JSON report endpoint so we get the exact
            # same shape the UI shows. We import lazily to avoid a cycle.
            from fastapi.routing import APIRoute
            target_path = f"/api/reports/{target_kind}"
            target = None
            for route in api.routes if hasattr(api, "routes") else []:
                if isinstance(route, APIRoute) and route.path == target_path and "GET" in route.methods:
                    target = route.endpoint
                    break
            if target is None:
                raise HTTPException(status_code=500, detail=f"Report endpoint for {kind!r} not registered.")

            # Build the kwargs each sibling endpoint accepts. Only pass
            # non-None values to avoid overriding the sibling's defaults.
            candidate = {
                "chapter_id": chapter_id, "tier_id": tier_id, "role": role,
                "status_filter": status_filter, "event_id": event_id,
                "parent_event_id": parent_event_id, "ticket_type": ticket_type,
                "year": year, "quarter": quarter, "month": month,
                "date_field": date_field, "cause_id": cause_id, "status": status,
                "recruiter_id": recruiter_id, "award_id": award_id,
            }
            import inspect
            sig = inspect.signature(target)
            kwargs = {k: v for k, v in candidate.items() if k in sig.parameters and v is not None}
            # `admin` is required only when the endpoint declares an `admin`
            # parameter; some legacy endpoints declare it as `_` (unused).
            if "admin" in sig.parameters:
                kwargs["admin"] = admin
            try:
                data = await target(**kwargs)
            except HTTPException:
                raise
            except Exception as e:
                logger.warning(f"PDF export delegate failed for {kind}: {e}")
                raise HTTPException(status_code=500, detail=f"Failed to render {kind} report: {e}")

            # Normalize response shape — some endpoints return a bare list,
            # others return a dict with an "items" key.
            if isinstance(data, dict) and "items" in data:
                docs = data["items"]
            elif isinstance(data, dict) and "rows" in data:
                docs = data["rows"]
            elif isinstance(data, list):
                docs = data
            else:
                docs = []

        cols_meta = _PDF_COLUMNS[kind]
        # Iter 130 — apply the column whitelist if the admin sent one.
        # Column keys are the second tuple element in _PDF_COLUMNS entries.
        if columns:
            wanted = {c.strip() for c in columns.split(",") if c.strip()}
            filtered = [c for c in cols_meta if c[1] in wanted]
            if filtered:
                cols_meta = filtered
        column_labels = [c[0] for c in cols_meta]
        col_weights = [c[2] if len(c) >= 3 else 1.0 for c in cols_meta]
        rows = _rows_for_pdf_with_cols(cols_meta, kind, docs)
        pretty_kind = kind.replace("-", " ").title().replace("Rsvps", "RSVPs")
        subtitle_parts = []
        if year:    subtitle_parts.append(f"Year {year}")
        if quarter: subtitle_parts.append(f"Q{quarter}")
        if month:   subtitle_parts.append(f"Month {month}")
        subtitle_parts.append(f"{len(rows)} rows")
        # Rekey rows so _pdf_response can look them up by column label.
        keyed_rows = []
        for r in rows:
            keyed_rows.append({label: r.get(key) for (label, key, *_rest) in cols_meta})
        return _pdf_response(
            title=f"AOP · {pretty_kind} Report",
            columns=column_labels,
            rows=keyed_rows,
            filename=f"aop-{kind}-report-{iso(now_utc())[:10]}.pdf",
            subtitle=" · ".join(subtitle_parts),
            col_weights=col_weights,
        )
