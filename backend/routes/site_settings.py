"""Site settings (hero copy, footer, home-page composition) routes."""
import re
from typing import Optional, List, Dict
from fastapi import Depends, HTTPException
from pydantic import BaseModel, Field, field_validator

from models import PageBlockIn, PAGE_BLOCK_TYPES


SETTINGS_DOC_ID = "site_settings_v1"

# Accept https URLs OR relative /path paths from our own uploads OR data URIs.
# Empty string is allowed for in-progress saves before an upload completes.
_URL_RE = re.compile(r"^(https?://[^\s]+|/[^\s]*|data:[^\s]+)?$")


def _validate_url_field(v):
    if v is None:
        return v
    v = (v or "").strip()
    if v and not _URL_RE.match(v):
        raise ValueError("Must be a full URL (https://…) or a /path/to/file")
    return v


def make_default_settings(iso, now_utc):
    return {
        "id": SETTINGS_DOC_ID,
        "hero_eyebrow": "Alpha Omega Phi Military Fraternity & Sorority, Inc.",
        "hero_headline": "Service. Honor. Brotherhood. Sisterhood.",
        "hero_subtext": "Veterans and service members from every branch — bonded for life.",
        "hero_cta_label": "Become a member",
        "hero_cta_href": "/apply",
        "footer_text": "© Alpha Omega Phi Military Fraternity & Sorority, Inc. — All rights reserved.",
        # Ordered list of profile-page sections. Admin can reorder via drag-drop
        # to apply ONE layout to every member's profile. Each entry is a
        # stable section key (built-in) OR a custom field defined alongside.
        # Members see the order; built-in sections are always preserved on the
        # backend (you can hide them via "visible:false") so we never lose
        # functionality on misconfiguration.
        "profile_layout": [
            {"key": "identity", "visible": True, "label": "Identity"},
            {"key": "contact", "visible": True, "label": "Contact"},
            {"key": "fraternity", "visible": True, "label": "Fraternity Details"},
            {"key": "languages", "visible": True, "label": "Languages"},
            {"key": "education", "visible": True, "label": "Civilian Education"},
            {"key": "social", "visible": True, "label": "Social Links"},
        ],
        # Up to 12 admin-defined custom fields rendered as a "Custom Fields"
        # section on the member profile form. Each field stores into
        # users.custom_fields[<key>]. Types: text / textarea / date / number / select.
        "profile_custom_fields": [],
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
            "leaderboard": True,
            "family_pulse": True,
            "upcoming_events": True,
            "news": True,
        },
        "home_blocks_top": [],
        "home_blocks_bottom": [],
        "leadership_team_eyebrow": "National board",
        "leadership_team_title": "Leadership Team",
        "leadership_team_items": [
            {
                "term": "2024-2026",
                "image_url": "https://customer-assets.emergentagent.com/job_club-express-lite/artifacts/4092ts0o_Kendra_Brandy_Banner_2074356465.jpg",
                "alt": "2024-2026 Leadership Team — Kendra Garrett & Brandy Brodie",
            },
            {
                "term": "2026-2028",
                "image_url": "https://customer-assets.emergentagent.com/job_club-express-lite/artifacts/oqcv3tss_Sheron_Tana_Banner_743849018.jpg",
                "alt": "2026-2028 Leadership Team — Sheron Andrews & Tana Blue",
            },
        ],
        "founders_section_eyebrow": "Founders",
        "founders_section_title": "Meet our Founders",
        "founders_items": [
            {"name": "Christian", "image_url": "https://customer-assets.emergentagent.com/job_club-express-lite/artifacts/2i9inws2_Christian.jpg", "role": "Founder"},
            {"name": "Cory", "image_url": "https://customer-assets.emergentagent.com/job_club-express-lite/artifacts/ug9oq343_Cory.jpg", "role": "Founder"},
            {"name": "Ken", "image_url": "https://customer-assets.emergentagent.com/job_club-express-lite/artifacts/ao1sl6gp_Ken.jpg", "role": "Founder"},
            {"name": "Lekita", "image_url": "https://customer-assets.emergentagent.com/job_club-express-lite/artifacts/p1mxh7ni_Lekita.jpg", "role": "Founder"},
        ],
        "updated_at": iso(now_utc()),
    }


class LeadershipItemIn(BaseModel):
    term: str = Field(min_length=1, max_length=80)
    image_url: str = Field("", max_length=600)
    alt: str = Field("", max_length=300)

    @field_validator("image_url")
    @classmethod
    def _check_image_url(cls, v: str) -> str:
        return _validate_url_field(v)


class FounderItemIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    image_url: str = Field("", max_length=600)
    role: str = Field("", max_length=120)  # e.g. "Founder", "Past President"

    @field_validator("image_url")
    @classmethod
    def _check_image_url(cls, v: str) -> str:
        return _validate_url_field(v)


class ProfileLayoutItem(BaseModel):
    key: str = Field(min_length=1, max_length=60)
    visible: bool = True
    label: str = Field("", max_length=120)


class ProfileCustomField(BaseModel):
    """Admin-defined custom profile field. Keys are normalized to snake_case
    on the client; we trust them here but cap length and type."""
    key: str = Field(min_length=1, max_length=60, pattern=r"^[a-z0-9_]+$")
    label: str = Field(min_length=1, max_length=120)
    type: str = Field("text")  # text|textarea|date|number|select
    options: List[str] = Field(default_factory=list, max_length=30)
    required: bool = False
    help_text: str = Field("", max_length=200)


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
    leadership_team_title: Optional[str] = Field(None, max_length=200)
    leadership_team_eyebrow: Optional[str] = Field(None, max_length=120)
    leadership_team_items: Optional[List[LeadershipItemIn]] = Field(None, max_length=10)
    founders_section_title: Optional[str] = Field(None, max_length=200)
    founders_section_eyebrow: Optional[str] = Field(None, max_length=120)
    founders_items: Optional[List[FounderItemIn]] = Field(None, max_length=12)
    profile_layout: Optional[List[ProfileLayoutItem]] = Field(None, max_length=40)
    profile_custom_fields: Optional[List[ProfileCustomField]] = Field(None, max_length=12)


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
        if "leaderboard" not in sec:
            sec["leaderboard"] = True
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
