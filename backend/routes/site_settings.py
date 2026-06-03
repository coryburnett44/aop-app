"""Site settings (hero copy, footer, home-page composition) routes."""
from typing import Optional, List, Dict
from fastapi import Depends, HTTPException
from pydantic import BaseModel, Field

from models import PageBlockIn, PAGE_BLOCK_TYPES


SETTINGS_DOC_ID = "site_settings_v1"


def make_default_settings(iso, now_utc):
    return {
        "id": SETTINGS_DOC_ID,
        "hero_eyebrow": "Alpha Omega Phi Military Fraternity & Sorority, Inc.",
        "hero_headline": "Service. Honor. Brotherhood. Sisterhood.",
        "hero_subtext": "Veterans and service members from every branch — bonded for life.",
        "hero_cta_label": "Become a member",
        "hero_cta_href": "/apply",
        "footer_text": "© Alpha Omega Phi Military Fraternity & Sorority, Inc. — All rights reserved.",
        "footer_links": [
            {"label": "About", "href": "/about"},
            {"label": "Contact", "href": "mailto:info@aop-app.org"},
        ],
        "page_titles": {},
        "nav_labels": {},
        "home_sections": {
            "founders": True,
            "hero_text": True,
            "countdown": True,
            "pillars": True,
            "leadership_team": True,
            "family_pulse": True,
            "upcoming_events": True,
            "news": True,
        },
        "home_blocks_top": [],
        "home_blocks_bottom": [],
        "updated_at": iso(now_utc()),
    }


class SiteSettingsIn(BaseModel):
    hero_eyebrow: Optional[str] = Field(None, max_length=300)
    hero_headline: Optional[str] = Field(None, max_length=300)
    hero_subtext: Optional[str] = Field(None, max_length=600)
    hero_cta_label: Optional[str] = Field(None, max_length=120)
    hero_cta_href: Optional[str] = Field(None, max_length=300)
    footer_text: Optional[str] = Field(None, max_length=1000)
    footer_links: Optional[List[Dict[str, str]]] = Field(None, max_length=20)
    page_titles: Optional[Dict[str, str]] = None
    nav_labels: Optional[Dict[str, str]] = None
    home_sections: Optional[Dict[str, bool]] = None
    home_blocks_top: Optional[List[PageBlockIn]] = Field(None, max_length=50)
    home_blocks_bottom: Optional[List[PageBlockIn]] = Field(None, max_length=50)


def register(api, *, db, admin_tab_dep, iso, now_utc):
    """Wire the /site-settings routes onto api using supplied deps."""

    async def _ensure_site_settings():
        existing = await db.site_settings.find_one({"id": SETTINGS_DOC_ID})
        defaults = make_default_settings(iso, now_utc)
        if not existing:
            await db.site_settings.insert_one(dict(defaults))
            return
        to_set = {}
        for k, v in defaults.items():
            if k not in existing:
                to_set[k] = v
        sec = existing.get("home_sections") or {}
        sec_updated = False
        if "leadership_team" not in sec:
            sec["leadership_team"] = True
            sec_updated = True
        if "secondary_banner" in sec:
            sec.pop("secondary_banner", None)
            sec_updated = True
        if sec_updated:
            to_set["home_sections"] = sec
        if to_set:
            await db.site_settings.update_one({"id": SETTINGS_DOC_ID}, {"$set": to_set})

    # Expose to server.py for any startup callers that need it
    register.ensure = _ensure_site_settings

    @api.get("/site-settings")
    async def get_site_settings():
        await _ensure_site_settings()
        s = await db.site_settings.find_one({"id": SETTINGS_DOC_ID}, {"_id": 0})
        return s

    @api.put("/site-settings")
    async def update_site_settings(body: SiteSettingsIn, _: dict = Depends(admin_tab_dep("pages"))):
        await _ensure_site_settings()
        updates = {k: v for k, v in body.model_dump().items() if v is not None}
        for blk_key in ("home_blocks_top", "home_blocks_bottom"):
            if blk_key in updates:
                for b in updates[blk_key]:
                    if b.get("type") not in PAGE_BLOCK_TYPES:
                        raise HTTPException(status_code=400, detail=f"Invalid block type in {blk_key}: {b.get('type')}")
        updates["updated_at"] = iso(now_utc())
        await db.site_settings.update_one({"id": SETTINGS_DOC_ID}, {"$set": updates})
        s = await db.site_settings.find_one({"id": SETTINGS_DOC_ID}, {"_id": 0})
        return s
