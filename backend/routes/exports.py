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
from typing import Optional

from fastapi import Depends, HTTPException, Response
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter, landscape
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import (
    SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, PageBreak,
)


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

    def _pdf_response(title: str, columns: list, rows: list, filename: str, subtitle: str = ""):
        """Renders a landscape PDF with a title, an optional subtitle,
        and a table of the given columns/rows. Long text cells wrap via
        the paragraph flowable so extended reasons/notes stay readable."""
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
        cell = ParagraphStyle("cell", parent=styles["Normal"], fontSize=8, leading=10)
        story = [
            Paragraph(title, h1),
            Paragraph(subtitle or f"Generated {iso(now_utc())} · {len(rows)} rows", h2),
        ]
        if not rows:
            story.append(Paragraph("<i>No data for the selected filters.</i>", cell))
        else:
            # Build table data — header row + one row per record. Wrap
            # every cell in Paragraph so long text doesn't clip.
            header = [Paragraph(f"<b>{c}</b>", cell) for c in columns]
            data = [header]
            for r in rows:
                data.append([Paragraph(_fmt_cell(r.get(c)), cell) for c in columns])
            # Give each column an equal share of the page width.
            page_w = landscape(letter)[0] - 0.8 * inch
            col_w = [page_w / max(1, len(columns))] * len(columns)
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
        "chapter", "tier", "role", "admin_role",
        "status", "is_lifetime_member", "join_date", "created_at",
        "membership_started_at", "membership_expires_at",
        "outstanding_balance_total", "total_paid",
        "hours_approved_total", "hours_pending_total",
        "donations_total", "recruits_count",
        "awards", "events_attended", "rsvps",
        "email_opt_out", "sms_opt_out",
    ]

    @api.get("/admin/members/export.csv")
    async def export_members_csv(
        admin: dict = Depends(admin_tab_dep("members")),
    ):
        """Full-fat member directory export. Includes personally-identifying
        information — restrict access via the members admin tab dep."""
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

            # Address is stored as a nested dict or as flat fields — normalize.
            addr = u.get("address") or {}
            if isinstance(addr, str):
                addr_line = addr; city = state = postal = country = ""
            else:
                addr_line = addr.get("line1") or addr.get("street") or ""
                city = addr.get("city") or ""
                state = addr.get("state") or ""
                postal = addr.get("postal_code") or addr.get("zip") or ""
                country = addr.get("country") or ""

            chapter = chapters.get(u.get("chapter_id"))
            tier = tiers.get(u.get("tier_id"))
            rows.append({
                "id": uid,
                "name": u.get("name", ""),
                "email": u.get("email", ""),
                "phone": u.get("phone", ""),
                "gender": u.get("gender", ""),
                "birth_date": (u.get("birth_date") or "")[:10],
                "address": addr_line,
                "city": city,
                "state": state,
                "postal_code": postal,
                "country": country,
                "chapter": chapter.get("name", "") if chapter else "",
                "tier": tier.get("name", "") if tier else "",
                "role": u.get("role", ""),
                "admin_role": u.get("admin_role", ""),
                "status": u.get("status", ""),
                "is_lifetime_member": bool(u.get("is_lifetime_member")),
                "join_date": (u.get("join_date") or "")[:10],
                "created_at": (u.get("created_at") or "")[:10],
                "membership_started_at": (u.get("membership_started_at") or "")[:10],
                "membership_expires_at": (u.get("membership_expires_at") or "")[:10],
                "outstanding_balance_total": u.get("outstanding_balance_total", 0),
                "total_paid": u.get("total_paid", 0),
                "hours_approved_total": round(hrs_by_status.get("approved", 0), 2),
                "hours_pending_total": round(hrs_by_status.get("pending", 0), 2),
                "donations_total": round(donations_total, 2),
                "recruits_count": recruits_count,
                "awards": awards_str,
                "events_attended": events_attended,
                "rsvps": rsvps_str,
                "email_opt_out": bool(u.get("email_opt_out")),
                "sms_opt_out": bool(u.get("sms_opt_out")),
            })

        fname = f"aop-members-{iso(now_utc())[:10]}.csv"
        return _csv_response(rows, _CSV_COLUMNS, fname)

    # =====================================================================
    # 2) PDF exports — one per report kind. Delegates to the JSON handler
    # so a filter tweak on the report shows up in the PDF automatically.
    # =====================================================================
    _PDF_COLUMNS = {
        "members": [
            ("Name", "name"),
            ("Email", "email"),
            ("Chapter", "chapter_name"),
            ("Tier", "tier_name"),
            ("Status", "status"),
            ("Joined", "join_date"),
            ("Expires", "membership_expires_at"),
            ("Balance", "outstanding_balance_total"),
        ],
        "rsvps": [
            ("Member", "user_name"),
            ("Event", "event_title"),
            ("Ticket", "ticket_type"),
            ("Guests", "guest_count"),
            ("RSVP'd", "rsvped_at"),
            ("Event start", "event_start_at"),
        ],
        "hours": [
            ("Member", "user_name"),
            ("Chapter", "chapter_name"),
            ("Date", "date"),
            ("Hours", "hours"),
            ("Type", "event_type"),
            ("Agency", "agency_name"),
            ("Activity", "activity"),
            ("Status", "status"),
        ],
        "donations": [
            ("Member", "user_name"),
            ("Cause", "cause_name"),
            ("Amount", "amount"),
            ("Method", "method"),
            ("Status", "status"),
            ("Date", "created_at"),
        ],
    }

    def _rows_for_pdf(kind: str, docs: list) -> list:
        """Flatten each record's fields into a plain-dict row keyed by
        the column keys defined in _PDF_COLUMNS[kind]. Handles the
        camelCased shapes each /reports endpoint returns."""
        cols = _PDF_COLUMNS[kind]
        out = []
        for d in docs:
            row = {}
            for _label, key in cols:
                v = d.get(key)
                # Common nested lookups per kind.
                if v is None and kind == "members":
                    if key == "chapter_name":
                        v = (d.get("chapter") or {}).get("name") if isinstance(d.get("chapter"), dict) else d.get("chapter_name")
                    elif key == "tier_name":
                        v = (d.get("tier") or {}).get("name") if isinstance(d.get("tier"), dict) else d.get("tier_name")
                if v is None and kind == "rsvps" and key == "guest_count":
                    v = len(d.get("guests") or [])
                if isinstance(v, str) and len(v) > 10 and v.endswith("Z"):
                    v = v[:10]
                elif isinstance(v, str) and "T" in v and len(v) >= 10:
                    v = v[:10]
                row[key] = v
            out.append(row)
        return out

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
        admin: dict = Depends(admin_tab_dep("reports")),
    ):
        kind = (kind or "").lower().strip()
        if kind not in _PDF_COLUMNS:
            raise HTTPException(
                status_code=400,
                detail=f"Unknown report kind {kind!r}. Supported: {sorted(_PDF_COLUMNS)}",
            )
        # Look up the sibling JSON report endpoint so we get the exact
        # same shape the UI shows. We import lazily to avoid a cycle.
        from fastapi.routing import APIRoute
        target_path = f"/api/reports/{kind}"
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
            "date_field": date_field, "admin": admin,
        }
        import inspect
        sig = inspect.signature(target)
        kwargs = {k: v for k, v in candidate.items() if k in sig.parameters and v is not None}
        # `admin` is always required by the endpoint.
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
        elif isinstance(data, list):
            docs = data
        else:
            docs = []

        cols_meta = _PDF_COLUMNS[kind]
        column_labels = [c[0] for c in cols_meta]
        rows = _rows_for_pdf(kind, docs)
        pretty_kind = kind.title().replace("Rsvps", "RSVPs")
        subtitle_parts = []
        if year:    subtitle_parts.append(f"Year {year}")
        if quarter: subtitle_parts.append(f"Q{quarter}")
        if month:   subtitle_parts.append(f"Month {month}")
        subtitle_parts.append(f"{len(rows)} rows · Generated {iso(now_utc())[:19].replace('T', ' ')} UTC")
        # Rekey rows so _pdf_response can look them up by column label.
        keyed_rows = []
        for r in rows:
            keyed_rows.append({label: r.get(key) for (label, key) in cols_meta})
        return _pdf_response(
            title=f"AOP · {pretty_kind} Report",
            columns=column_labels,
            rows=keyed_rows,
            filename=f"aop-{kind}-report-{iso(now_utc())[:10]}.pdf",
            subtitle=" · ".join(subtitle_parts),
        )
