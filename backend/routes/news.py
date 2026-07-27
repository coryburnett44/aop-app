"""News CRUD routes. Registered via register(api, deps) from server.py.

Iter 111: multi-image support (`images` list up to 5), layout `template` picker,
and public search via `?q=` on title / summary / body.

Iter 138: rich HTML body (`body_html`) + per-article `background_color`.

Iter 139: on CREATE, optionally blast an announcement email to every active,
opted-in member with the article title, summary, cover image and a
"Read the full story" button linking to `{FRONTEND_URL}/news/{id}`. Admins
can uncheck "Notify members via email" in the dialog to publish silently.
"""
import asyncio
import html as html_mod
import os
import re
import uuid
from typing import Optional

from fastapi import Depends, HTTPException

from models import NewsIn, NewsUpdateIn


def news_out(n: dict) -> dict:
    return {
        "id": n["id"],
        "title": n["title"],
        "summary": n.get("summary", ""),
        "body": n.get("body", ""),
        "body_html": n.get("body_html", "") or "",
        "background_color": n.get("background_color", "") or "",
        "cover_image": n.get("cover_image", ""),
        "images": n.get("images", []) or [],
        "template": n.get("template", "classic"),
        "tags": n.get("tags", []),
        "author_name": n.get("author_name", ""),
        "created_at": n.get("created_at"),
    }


def _abs_url(base: str, path_or_url: str) -> str:
    """Return `path_or_url` as an absolute URL. Passes through already-absolute
    URLs; prefixes the frontend base for relative ones. Empty string in → out."""
    if not path_or_url:
        return ""
    if path_or_url.startswith("http://") or path_or_url.startswith("https://"):
        return path_or_url
    if path_or_url.startswith("/"):
        return f"{base.rstrip('/')}{path_or_url}"
    return f"{base.rstrip('/')}/{path_or_url}"


def _build_announcement_html(*, title: str, summary: str, cover_image: str, article_url: str, base_url: str) -> str:
    """Email-client-safe HTML for the auto-announcement email. Inline styles
    only (Gmail/Outlook strip <style>). Cover image resolves through the same
    /api/files auth — but the shared inbox for admin-created posts is public
    photos, so we absolutize whatever the admin uploaded."""
    safe_title = html_mod.escape(title or "New from Alpha Omega Phi")
    safe_summary = html_mod.escape(summary or "")
    cover_abs = _abs_url(base_url, cover_image)
    parts: list[str] = []
    parts.append('<div style="max-width:600px;margin:0 auto;font-family:-apple-system,BlinkMacSystemFont,Segoe UI,Roboto,sans-serif;color:#0A2463;">')
    parts.append('<div style="padding:24px 8px;text-align:left;">')
    parts.append('<div style="font-size:11px;letter-spacing:0.14em;text-transform:uppercase;color:#C8102E;font-weight:700;">Alpha Omega Phi · News</div>')
    parts.append(f'<h1 style="font-size:26px;line-height:1.15;margin:12px 0 8px;color:#0A2463;font-weight:800;">{safe_title}</h1>')
    if cover_abs:
        parts.append(
            f'<div style="margin:16px 0;"><img alt="" src="{cover_abs}" '
            'style="display:block;width:100%;max-width:600px;height:auto;border-radius:12px;" /></div>'
        )
    if safe_summary:
        parts.append(f'<p style="font-size:16px;line-height:1.6;color:#334155;margin:12px 0 20px;">{safe_summary}</p>')
    # CTA button — table layout keeps Outlook happy.
    parts.append(
        '<table role="presentation" cellpadding="0" cellspacing="0" border="0" style="margin:8px 0 24px;"><tr><td '
        'style="background-color:#C8102E;border-radius:9999px;">'
        f'<a href="{article_url}" style="display:inline-block;padding:12px 26px;color:#ffffff;text-decoration:none;'
        'font-weight:700;font-size:15px;">Read the full story →</a></td></tr></table>'
    )
    parts.append(
        f'<p style="font-size:12px;color:#64748B;margin:16px 0 0;">Or open it directly: '
        f'<a href="{article_url}" style="color:#C8102E;">{safe_title}</a></p>'
    )
    parts.append('</div></div>')
    return "".join(parts)


def register(api, *, db, admin_tab_dep, iso, now_utc, send_bulk_email=None, logger=None):
    async def _send_new_article_emails(*, article: dict) -> dict:
        """Fire-and-forget style: iterate every active, opted-in member and
        send them the announcement. Sequential (not gather) to stay under any
        Resend / SMTP rate limits and match the existing blast loop."""
        if send_bulk_email is None:
            return {"sent": 0, "skipped": "send_bulk_email not wired"}
        base_url = (os.environ.get("FRONTEND_URL", "https://aop-app.org") or "").rstrip("/")
        article_url = f"{base_url}/news/{article['id']}"
        subject_tpl = article.get("title") or "New from Alpha Omega Phi"
        summary = article.get("summary") or ""
        cover = article.get("cover_image") or ""
        # Same audience rules the blast composer uses for the "active" segment.
        q = {
            "status_override": {"$ne": "deceased"},
            "email_opt_out": {"$ne": True},
            "email_prefs.blasts": {"$ne": False},
            "email": {"$nin": [None, ""]},
        }
        recipients = await db.users.find(q, {"_id": 0, "id": 1, "email": 1, "name": 1, "first_name": 1}).to_list(2000)
        blast_id = str(uuid.uuid4())
        # Insert the blast log up-front so admins see it in Email → History
        # immediately (even while the loop is still running for a large
        # roster). Counters are patched in place after each send.
        try:
            await db.email_blasts.insert_one({
                "id": blast_id,
                "subject": f"[News] {subject_tpl}",
                "segment": "active",
                "sent_count": 0,
                "failed_count": 0,
                "recipient_count": len(recipients),
                "sent_by_name": article.get("author_name") or "News auto-notify",
                "sent_at": iso(now_utc()),
                "kind": "news_announcement",
                "news_id": article["id"],
            })
        except Exception:
            pass
        sent = 0
        failed = 0
        for r in recipients:
            first = (r.get("first_name") or (r.get("name") or "").split(" ")[0] or "there").strip()
            per_html = _build_announcement_html(
                title=subject_tpl,
                summary=summary,
                cover_image=cover,
                article_url=article_url,
                base_url=base_url,
            )
            greeting = f'<p style="font-family:-apple-system,sans-serif;max-width:600px;margin:0 auto 4px;padding:0 8px;color:#334155;">Hi {html_mod.escape(first)},</p>'
            full_html = greeting + per_html
            try:
                await send_bulk_email(
                    to_email=r["email"],
                    subject=subject_tpl,
                    html_body=full_html,
                    recipient_id=r.get("id", ""),
                    tags=[
                        {"name": "blast_id", "value": blast_id},
                        {"name": "type", "value": "news_announcement"},
                        {"name": "news_id", "value": article["id"]},
                    ],
                )
                sent += 1
            except Exception as e:
                failed += 1
                if logger:
                    logger.error(f"[news-announce] send failed for {r.get('email')}: {e}")
        try:
            await db.email_blasts.update_one(
                {"id": blast_id},
                {"$set": {"sent_count": sent, "failed_count": failed}},
            )
        except Exception:
            pass
        if logger:
            logger.info(f"[news-announce] article={article['id']} sent={sent} failed={failed}")
        return {"sent": sent, "failed": failed, "blast_id": blast_id}

    @api.get("/news")
    async def list_news(q: Optional[str] = None):
        """List news articles, newest first. Optional `q` filters on
        title / summary / body via case-insensitive regex. We escape the
        user input to prevent regex injection but still allow substring
        matches (which is what the member-facing search bar sends)."""
        query: dict = {}
        if q and q.strip():
            safe = re.escape(q.strip())
            query = {
                "$or": [
                    {"title": {"$regex": safe, "$options": "i"}},
                    {"summary": {"$regex": safe, "$options": "i"}},
                    {"body": {"$regex": safe, "$options": "i"}},
                    {"body_html": {"$regex": safe, "$options": "i"}},
                    {"tags": {"$regex": safe, "$options": "i"}},
                ],
            }
        cursor = db.news.find(query, {"_id": 0}).sort("created_at", -1).limit(200)
        items = await cursor.to_list(200)
        return [news_out(n) for n in items]

    @api.get("/news/{news_id}")
    async def get_news(news_id: str):
        n = await db.news.find_one({"id": news_id}, {"_id": 0})
        if not n:
            raise HTTPException(status_code=404, detail="News not found")
        return news_out(n)

    @api.post("/news")
    async def create_news(body: NewsIn, notify: bool = True, admin: dict = Depends(admin_tab_dep("news"))):
        """Create a news article. When `notify=true` (default) every active,
        opted-in member is emailed the title + summary + a Read-more link.
        Pass `?notify=false` to publish silently (edits, back-dated posts)."""
        nid = str(uuid.uuid4())
        doc = body.model_dump()
        doc.update({"id": nid, "author_name": admin.get("name", "Admin"), "created_at": iso(now_utc())})
        await db.news.insert_one(doc)
        # Strip the ObjectId Motor injects into `doc` so this dict is JSON-safe
        # (same footgun we fixed in Regions CRUD).
        doc.pop("_id", None)
        if notify:
            # Don't block the create response on the (potentially long) email
            # loop — kick it off as a background task and return immediately.
            asyncio.create_task(_send_new_article_emails(article=doc))
        return news_out(doc)

    @api.put("/news/{news_id}")
    async def update_news(news_id: str, body: NewsUpdateIn, _: dict = Depends(admin_tab_dep("news"))):
        updates = {k: v for k, v in body.model_dump().items() if v is not None}
        if updates:
            await db.news.update_one({"id": news_id}, {"$set": updates})
        n = await db.news.find_one({"id": news_id}, {"_id": 0})
        if not n:
            raise HTTPException(status_code=404, detail="News not found")
        return news_out(n)

    @api.delete("/news/{news_id}")
    async def delete_news(news_id: str, _: dict = Depends(admin_tab_dep("news"))):
        await db.news.delete_one({"id": news_id})
        return {"ok": True}
