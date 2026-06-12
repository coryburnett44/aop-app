"""Pydantic models for the AOP backend.

Extracted from server.py to reduce monolith size. Pure data classes only —
no DB access, no business logic. Imported back into server.py.
"""
from datetime import datetime
from typing import List, Optional, Literal, Dict, Any

from pydantic import BaseModel, EmailStr, Field


class RegisterIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=6)
    name: str = Field(min_length=1)
    city: Optional[str] = ""
    interests: Optional[List[str]] = []


class PublicApplicationIn(BaseModel):
    """Open-registration application form. Applicant chooses their own password
    up-front; on admin approval, the password is set on the new user account and
    a 'you're approved' email is sent so they can sign in directly."""
    first_name: str = Field(min_length=1, max_length=80)
    last_name: str = Field(min_length=1, max_length=80)
    email: EmailStr
    password: str = Field(min_length=6, max_length=128)
    line_name: str = ""
    intake_line: str = ""
    intake_completed_at: str = ""
    address: str = ""
    city: str = ""
    state: str = ""
    zip_code: str = ""
    country: str = ""


class ApplicationReviewIn(BaseModel):
    action: Literal["approve", "reject"]
    note: Optional[str] = ""


class SetPasswordIn(BaseModel):
    token: str
    new_password: str = Field(min_length=6)


class LoginIn(BaseModel):
    # Accepts an email address OR a username. The field is named `email` for
    # backwards compatibility with existing clients (mobile, older frontend).
    email: str = Field(min_length=1)
    password: str


TITLE_CHOICES = Literal["Mr.", "Mrs.", "Ms.", "Miss", "Dr.", "Prof.", "Rev.", "Hon.", "Mx."]

MARITAL_STATUS_CHOICES = Literal["", "Single", "Engaged", "Domestic Partnership", "Married", "Divorced", "Widowed"]

PROFICIENCY_CHOICES = Literal["", "Native", "Fluent", "Advanced", "Intermediate", "Basic"]

DEGREE_LEVEL_CHOICES = Literal[
    "", "HS Diploma", "Trade Cert", "Associate", "Bachelors",
    "Masters", "Masters Certificate", "Doctorate", "Doctor of Philosophy",
]


class LanguageEntry(BaseModel):
    """One spoken-language profile entry. Up to 3 per user."""
    language: str = ""
    speaking: str = ""        # PROFICIENCY_CHOICES
    reading: str = ""
    writing: str = ""
    year_accomplished: Optional[int] = None


class CivilianDegreeEntry(BaseModel):
    """One civilian-degree entry. Up to 5 per user."""
    degree_level: str = ""    # DEGREE_LEVEL_CHOICES
    degree_type: str = ""     # e.g. "BS", "MBA", "Ph.D"
    field_of_study: str = ""
    institution: str = ""
    graduation_month: Optional[int] = None  # 1–12
    graduation_year: Optional[int] = None


RANK_CHOICES = Literal[
    "", "Grand Sirius", "Master Sirius", "Senior Sirius", "Advanced Sirius",
    "Junior Sirius", "Eagle", "Clover", "Guardian",
]


class AssignmentEntry(BaseModel):
    """One row of a member's assignment history. Admin-managed only."""
    start_date: str = ""        # ISO date 'YYYY-MM-DD' (or empty)
    end_date: str = ""          # ISO date or '' (interpreted as 'Current')
    is_current: bool = False
    chapter_id: str = ""        # optional FK to chapters
    chapter_name: str = ""      # snapshot — kept even if chapter renamed/deleted
    state: str = ""
    location: str = ""
    duty_title: str = ""
    rank: str = ""              # one of RANK_CHOICES


class ProfileUpdateIn(BaseModel):
    name: Optional[str] = None
    title: Optional[str] = None
    first_name: Optional[str] = None
    middle_name: Optional[str] = None
    last_name: Optional[str] = None
    line_name: Optional[str] = None
    intake_line: Optional[str] = None
    intake_completed_at: Optional[str] = None
    username: Optional[str] = None
    bio: Optional[str] = None
    city: Optional[str] = None
    phone: Optional[str] = None
    address: Optional[str] = None
    state: Optional[str] = None
    zip_code: Optional[str] = None
    country: Optional[str] = None
    birthdate: Optional[str] = None
    branch_of_service: Optional[str] = None
    marital_status: Optional[str] = None
    languages: Optional[List[LanguageEntry]] = None
    civilian_degrees: Optional[List[CivilianDegreeEntry]] = None
    custom_fields: Optional[Dict[str, Any]] = None
    interests: Optional[List[str]] = None
    avatar_url: Optional[str] = None
    chat_email_notifications: Optional[bool] = None
    chat_sms_notifications: Optional[bool] = None
    facebook_url: Optional[str] = None
    instagram_url: Optional[str] = None
    linkedin_url: Optional[str] = None
    tiktok_url: Optional[str] = None
    twitter_url: Optional[str] = None
    pinterest_url: Optional[str] = None
    youtube_url: Optional[str] = None
    website_url: Optional[str] = None


class StatusOverrideIn(BaseModel):
    status: Optional[Literal["active", "inactive", "grace", "expired", "deceased"]] = None
    deceased_at: Optional[str] = None


class ChapterIn(BaseModel):
    name: str
    state: str = ""
    region: str = ""
    school: str = ""
    city: str = ""
    founded_year: Optional[int] = None
    description: str = ""
    logo_url: str = ""


class ChapterUpdateIn(BaseModel):
    name: Optional[str] = None
    state: Optional[str] = None
    region: Optional[str] = None
    school: Optional[str] = None
    city: Optional[str] = None
    founded_year: Optional[int] = None
    description: Optional[str] = None
    logo_url: Optional[str] = None


class HoursLogIn(BaseModel):
    hours: float = Field(gt=0, le=1000)
    activity: str = Field(min_length=2)
    date: datetime
    event_type: Literal["aop_related", "other"] = "other"
    agency_name: str = Field(min_length=1)
    host_name: str = Field(min_length=1)
    host_email: EmailStr
    host_phone: str = Field(min_length=4)
    event_id: Optional[str] = None
    description: Optional[str] = None


class AdminHoursLogIn(BaseModel):
    """Admin-only relaxed variant. Admins are trusted to log on behalf of any
    member without filling every host-of-contact field. The hours go in as
    `approved` immediately since the admin's act of logging is the approval."""
    user_id: str
    hours: float = Field(gt=0, le=1000)
    date: datetime
    activity: Optional[str] = ""
    event_type: Literal["aop_related", "other"] = "aop_related"
    agency_name: Optional[str] = ""
    host_name: Optional[str] = ""
    host_email: Optional[str] = ""
    host_phone: Optional[str] = ""
    event_id: Optional[str] = None
    description: Optional[str] = None


OF_THE_YEAR_CATEGORIES = Literal[
    "member_of_year",
    "chapter_of_year",
    "top_cs_member",
    "top_cs_chapter",
    "top_fundraising_member",
    "top_fundraising_chapter",
    "top_recruiter",
]


class OfTheYearIn(BaseModel):
    """One winner per (category, year). The frontend chooses user_id for the
    *_member / *_recruiter categories, or chapter_id for the *_chapter ones."""
    category: OF_THE_YEAR_CATEGORIES
    year: int = Field(ge=1900, le=2100)
    user_id: Optional[str] = None
    chapter_id: Optional[str] = None
    note: Optional[str] = ""


class OfTheYearUpdateIn(BaseModel):
    year: Optional[int] = Field(default=None, ge=1900, le=2100)
    user_id: Optional[str] = None
    chapter_id: Optional[str] = None
    note: Optional[str] = None


class AwardGrantIn(BaseModel):
    user_id: str
    reason: str = ""
    granted_at: Optional[str] = None


class ChangePasswordIn(BaseModel):
    current_password: str
    new_password: str = Field(min_length=6)


class AdminCreateMemberIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=6)
    title: str = ""
    first_name: str = ""
    middle_name: str = ""
    last_name: str = ""
    name: Optional[str] = None
    line_name: str = ""
    intake_line: str = ""
    intake_completed_at: str = ""
    username: str = ""
    phone: str = ""
    city: str = ""
    address: str = ""
    state: str = ""
    zip_code: str = ""
    country: str = ""
    birthdate: str = ""
    branch_of_service: str = ""
    role: Literal["member", "admin"] = "member"
    admin_role: Optional[Literal["full", "membership_manager", "operations_manager", "governor_manager"]] = None
    allowed_tabs: Optional[List[str]] = None
    chapter_id: Optional[str] = None
    tier_id: Optional[str] = None
    member_status: Optional[Literal["active", "inactive", "grace", "expired", "deceased"]] = None
    join_date: Optional[datetime] = None


class AdminUpdateMemberIn(BaseModel):
    email: Optional[EmailStr] = None
    name: Optional[str] = None
    title: Optional[str] = None
    first_name: Optional[str] = None
    middle_name: Optional[str] = None
    last_name: Optional[str] = None
    line_name: Optional[str] = None
    intake_line: Optional[str] = None
    intake_completed_at: Optional[str] = None
    username: Optional[str] = None
    bio: Optional[str] = None
    city: Optional[str] = None
    phone: Optional[str] = None
    address: Optional[str] = None
    state: Optional[str] = None
    zip_code: Optional[str] = None
    country: Optional[str] = None
    birthdate: Optional[str] = None
    branch_of_service: Optional[str] = None
    marital_status: Optional[str] = None
    languages: Optional[List[LanguageEntry]] = None
    civilian_degrees: Optional[List[CivilianDegreeEntry]] = None
    custom_fields: Optional[Dict[str, Any]] = None
    interests: Optional[List[str]] = None
    avatar_url: Optional[str] = None
    role: Optional[Literal["member", "admin"]] = None
    admin_role: Optional[Literal["full", "membership_manager", "operations_manager", "governor_manager"]] = None
    allowed_tabs: Optional[List[str]] = None
    chapter_id: Optional[str] = None
    tier_id: Optional[str] = None
    membership_expires_at: Optional[datetime] = None
    join_date: Optional[datetime] = None
    member_status: Optional[Literal["active", "inactive", "grace", "expired", "deceased"]] = None
    deceased_at: Optional[str] = None
    trust_zeffy: Optional[bool] = None
    new_password: Optional[str] = None
    assignment_history: Optional[List[AssignmentEntry]] = None


class TransactionIn(BaseModel):
    user_id: str
    type: Literal["renewal", "donation", "credit", "fee", "adjustment"]
    amount: float
    currency: str = "USD"
    description: str = ""
    status: Literal["completed", "pending", "refunded"] = "completed"


class EventIn(BaseModel):
    title: str
    description: str = ""
    location: str = ""
    start_at: datetime
    end_at: Optional[datetime] = None
    capacity: int = 0
    cover_image: str = ""
    category: str = "general"
    price: float = 0.0
    parent_event_id: Optional[str] = None
    allows_ticket_types: bool = False
    enabled_ticket_types: List[str] = []
    cancelled: bool = False
    cancellation_note: str = ""
    is_paid: bool = False
    payment_url: str = ""
    payment_amount: float = 0.0


class EventUpdateIn(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    location: Optional[str] = None
    start_at: Optional[datetime] = None
    end_at: Optional[datetime] = None
    capacity: Optional[int] = None
    cover_image: Optional[str] = None
    category: Optional[str] = None
    price: Optional[float] = None
    parent_event_id: Optional[str] = None
    allows_ticket_types: Optional[bool] = None
    enabled_ticket_types: Optional[List[str]] = None
    cancelled: Optional[bool] = None
    cancellation_note: Optional[str] = None
    is_paid: Optional[bool] = None
    payment_url: Optional[str] = None
    payment_amount: Optional[float] = None


TicketType = Literal["vip", "all_access", "general", "guest", "speaker", "volunteer"]

# All defined ticket types, in display order. Admin selects which subset applies
# per event; an empty enabled_ticket_types list means "this event has no ticket
# types" (members RSVP without choosing one).
ALL_TICKET_TYPES: List[str] = ["vip", "all_access", "general", "guest", "speaker", "volunteer"]


class GuestIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    email: Optional[str] = ""
    phone: Optional[str] = ""
    ticket_type: Optional[TicketType] = "general"


class EventRsvpIn(BaseModel):
    guests: List[GuestIn] = []
    ticket_type: Optional[TicketType] = "general"


class EventPaymentConfirmIn(BaseModel):
    """Member submits the Zeffy receipt # after paying for a paid event.
    Mirrors ZeffyConfirmIn — auto-approves only when admin trusts the member
    (trust_zeffy) AND the receipt matches a known Zeffy format."""
    confirmation: str = Field(min_length=2, max_length=200)
    guests: List[GuestIn] = []
    ticket_type: Optional[TicketType] = "general"


class NewsIn(BaseModel):
    title: str
    summary: str = ""
    body: str
    cover_image: str = ""
    tags: List[str] = []


class NewsUpdateIn(BaseModel):
    title: Optional[str] = None
    summary: Optional[str] = None
    body: Optional[str] = None
    cover_image: Optional[str] = None
    tags: Optional[List[str]] = None


PAGE_BLOCK_TYPES = ("heading", "subheading", "paragraph", "image", "button", "divider", "html", "spacer", "columns", "video")


class PageBlockIn(BaseModel):
    id: str
    type: str
    props: Dict[str, Any] = {}


class PageIn(BaseModel):
    slug: str
    title: str
    body: str = ""
    blocks: Optional[List[PageBlockIn]] = None


class PageUpdateIn(BaseModel):
    title: Optional[str] = None
    body: Optional[str] = None
    blocks: Optional[List[PageBlockIn]] = None


class AIEventReq(BaseModel):
    title: str
    topic: str = ""
    audience: str = "club members"
    tone: str = "friendly"


class AIEmailReq(BaseModel):
    subject: str
    goal: str
    tone: str = "warm"


class ForgotPasswordIn(BaseModel):
    email: EmailStr


class ResetPasswordIn(BaseModel):
    token: str
    new_password: str = Field(min_length=6)


class VerifyEmailIn(BaseModel):
    token: str


class RoleUpdateIn(BaseModel):
    role: Literal["member", "admin"]


class TierIn(BaseModel):
    name: str
    order: int = 0
    color: str = "#E86A58"
    annual_dues: float = 60.0
    description: str = ""


class TierUpdateIn(BaseModel):
    name: Optional[str] = None
    order: Optional[int] = None
    color: Optional[str] = None
    annual_dues: Optional[float] = None
    description: Optional[str] = None


class AwardIn(BaseModel):
    name: str
    description: str = ""
    icon: str = "trophy"
    color: str = "#F9D466"


class AwardUpdateIn(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    icon: Optional[str] = None
    color: Optional[str] = None


class HoursReviewIn(BaseModel):
    status: Literal["pending", "approved", "rejected"]
    note: Optional[str] = ""
    # Admin can adjust the hours value when approving (e.g. member submitted 5.0
    # but only 4.5 were actually worked). Allowing this on both initial review
    # and post-approval edits keeps reconciliation easy.
    hours: Optional[float] = Field(None, gt=0, le=1000)
    activity: Optional[str] = None
    agency_name: Optional[str] = None
    event_type: Optional[Literal["aop_related", "other"]] = None


class AssignChapterIn(BaseModel):
    chapter_id: Optional[str] = None


class AssignTierIn(BaseModel):
    tier_id: Optional[str] = None
    extend_days: Optional[int] = None


class PhotoMetaIn(BaseModel):
    title: Optional[str] = ""
    album: Optional[str] = "general"


class DocumentMetaIn(BaseModel):
    title: Optional[str] = ""
    category: Optional[str] = "general"
    description: Optional[str] = ""
