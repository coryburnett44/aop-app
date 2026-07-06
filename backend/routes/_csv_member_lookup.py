"""Shared member-resolution helper for admin CSV importers.

Both the Hours (`/api/hours/admin/csv`) and Donations (`/api/donations/admin/csv`)
CSV importers need to look up an existing member per row. Historically the
only accepted lookup key was `member_email` (or `email`), which broke for
chapters whose members use a different email day-to-day than the one on file.

This helper adds two safe name-based fallbacks while keeping the existing
email path the preferred match. Accepted CSV columns (any one is enough):

  * `member_email` (or `email`)       - exact, case-insensitive
  * `full_name` (or `name`)           - case-insensitive match on
                                        `users.name` (punctuation-tolerant)
  * `first_name` + `last_name`        - case-insensitive match on
                                        `users.first_name` AND `users.last_name`
                                        (punctuation-tolerant)

Name matching normalises punctuation (periods, commas, apostrophes) and
collapses whitespace so `"Brandy L. Brodie"` in the DB still matches
`"Brandy Brodie"` in the CSV (and vice versa) — a lax variant is only
attempted when the exact match fails, and ambiguous relaxed matches still
raise the same disambiguation error.

Resolution order per row: email → full_name → first_name+last_name. The first
key supplied in the row decides which lookup is used; we do NOT silently fall
through to a name match when an email is given but unmatched (that almost
always means a typo the admin should see, not a wrong-email-on-file case).

Ambiguity is treated as a hard error: if a name matches >1 member the row
fails with a clear message asking the admin to supply an email/middle initial
to disambiguate. This is intentional — silently picking a member would corrupt
hours and donation records.

Usage from a route handler:

    from routes._csv_member_lookup import (
        member_lookup_columns_present, prefetch_member_lookup,
        resolve_member_for_row, MEMBER_LOOKUP_HEADER_HINT,
    )

    rows = list(reader)
    headers_lower = {(h or '').strip().lower() for h in reader.fieldnames}
    if not member_lookup_columns_present(headers_lower):
        raise HTTPException(400, MEMBER_LOOKUP_HEADER_HINT)

    index = await prefetch_member_lookup(db, rows)
    for row in rows:
        member, err = resolve_member_for_row(row, index)
        ...

The pre-fetch does a single Mongo `find` covering every email + name candidate
across the whole file, so a 1,000-row import still costs one DB round-trip
for member resolution.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Iterable, Optional


# Column aliases. We accept either of these and read them with .lower() keys.
EMAIL_COLS = ("member_email", "email")
FULL_NAME_COLS = ("full_name", "name")
FIRST_NAME_COLS = ("first_name", "firstname", "given_name")
LAST_NAME_COLS = ("last_name", "lastname", "surname", "family_name")


MEMBER_LOOKUP_HEADER_HINT = (
    "CSV must include either a 'member_email' column, a 'full_name' column, "
    "or both 'first_name' and 'last_name' columns so each row can be linked "
    "to an existing member."
)


def _col(row: dict, names: Iterable[str]) -> str:
    """Return the first non-empty value from `row` for any of `names`, after
    trim. `row` is expected to be already lower-cased on keys."""
    for n in names:
        v = row.get(n)
        if v is None:
            continue
        s = str(v).strip()
        if s:
            return s
    return ""


def member_lookup_columns_present(headers_lower: set[str]) -> bool:
    """True iff the CSV header includes at least one of the supported lookup
    column groups (email OR full_name OR first_name+last_name)."""
    if any(c in headers_lower for c in EMAIL_COLS):
        return True
    if any(c in headers_lower for c in FULL_NAME_COLS):
        return True
    has_first = any(c in headers_lower for c in FIRST_NAME_COLS)
    has_last = any(c in headers_lower for c in LAST_NAME_COLS)
    return has_first and has_last


@dataclass
class MemberLookupIndex:
    """In-memory lookup built once per CSV import."""
    by_email: dict[str, dict] = field(default_factory=dict)
    # by_full_name / by_first_last hold LISTS to surface ambiguity. After
    # building, callers check `len(list) > 1` for the ambiguous case.
    by_full_name: dict[str, list[dict]] = field(default_factory=dict)
    by_first_last: dict[tuple[str, str], list[dict]] = field(default_factory=dict)
    # Punctuation-relaxed variants — used only if the exact key misses. Same
    # ambiguity semantics apply.
    by_full_name_relaxed: dict[str, list[dict]] = field(default_factory=dict)
    by_first_last_relaxed: dict[tuple[str, str], list[dict]] = field(default_factory=dict)


_PUNCT_RE = re.compile(r"[.,'’\"()`~!?-]+")
_WS_RE = re.compile(r"\s+")


def _relax(name: str) -> str:
    """Return a punctuation/whitespace-normalised copy of `name` for lax
    matching. Removes periods, commas, apostrophes, hyphens, etc., collapses
    runs of whitespace, and lowercases."""
    if not name:
        return ""
    s = _PUNCT_RE.sub(" ", name.lower())
    return _WS_RE.sub(" ", s).strip()


def _normalize_row_keys(rows: list[dict]) -> list[dict]:
    """Return a copy of `rows` with each row's keys lower-cased + stripped.
    Values are NOT trimmed here (route handlers do their own trim and care
    about original whitespace for diagnostics)."""
    out = []
    for r in rows:
        out.append({(k or "").strip().lower(): v for k, v in r.items() if k})
    return out


async def prefetch_member_lookup(db, rows: list[dict]) -> MemberLookupIndex:
    """Build a `MemberLookupIndex` over every candidate email + name appearing
    in `rows`, using a single Mongo round-trip. `rows` may have either
    original-case keys (we lower-case internally) or already-lowered keys."""
    norm = _normalize_row_keys(rows)
    emails: set[str] = set()
    full_names: set[str] = set()
    first_last_pairs: set[tuple[str, str]] = set()

    for r in norm:
        email = _col(r, EMAIL_COLS).lower()
        if email:
            emails.add(email)
        full = _col(r, FULL_NAME_COLS)
        if full:
            full_names.add(full.lower())
        fn = _col(r, FIRST_NAME_COLS)
        ln = _col(r, LAST_NAME_COLS)
        if fn and ln:
            first_last_pairs.add((fn.lower(), ln.lower()))

    # Build a single $or query that pulls every candidate user the file might
    # reference. We use a case-insensitive regex anchored with ^...$ because
    # Mongo indexes on email/name are case-sensitive by default and we want
    # admins to be able to type "Jane Doe" or "jane doe" indistinguishably.
    or_clauses: list[dict] = []
    if emails:
        or_clauses.extend(
            {"email": {"$regex": f"^{re.escape(e)}$", "$options": "i"}}
            for e in emails
        )
    for n in full_names:
        # Exact anchored match — cheap. Relaxed matching happens client-side
        # against the same result set below.
        or_clauses.append({"name": {"$regex": f"^{re.escape(n)}$", "$options": "i"}})
        # Also fetch anyone whose stored name contains the same last token —
        # this pulls "Brandy L. Brodie" when the CSV has "Brandy Brodie", so
        # the relaxed post-filter can then confirm.
        parts = n.split()
        if parts:
            last_tok = parts[-1]
            or_clauses.append({"last_name": {"$regex": f"^{re.escape(last_tok)}$", "$options": "i"}})
            or_clauses.append({"name": {"$regex": re.escape(last_tok), "$options": "i"}})
    for fn, ln in first_last_pairs:
        or_clauses.append({
            "$and": [
                {"first_name": {"$regex": f"^{re.escape(fn)}$", "$options": "i"}},
                {"last_name": {"$regex": f"^{re.escape(ln)}$", "$options": "i"}},
            ]
        })
        # Widen: pull anyone with the same last_name for relaxed post-match.
        or_clauses.append({"last_name": {"$regex": f"^{re.escape(ln)}$", "$options": "i"}})

    index = MemberLookupIndex()
    if not or_clauses:
        return index

    projection = {
        "_id": 0,
        "id": 1,
        "name": 1,
        "email": 1,
        "first_name": 1,
        "last_name": 1,
        "chapter_id": 1,
    }
    cursor = db.users.find({"$or": or_clauses}, projection)
    candidates = await cursor.to_list(length=10000)

    for u in candidates:
        em = (u.get("email") or "").lower().strip()
        if em:
            index.by_email[em] = u
        full = (u.get("name") or "").lower().strip()
        if full:
            index.by_full_name.setdefault(full, []).append(u)
        fn = (u.get("first_name") or "").lower().strip()
        ln = (u.get("last_name") or "").lower().strip()
        if fn and ln:
            index.by_first_last.setdefault((fn, ln), []).append(u)
        # Relaxed variants — strip punctuation so "Brandy L. Brodie" also
        # keys on "brandy l brodie" (and separately on the punctuation-free
        # "brandy brodie" via a first-token+last-token composite below).
        full_relaxed = _relax(u.get("name") or "")
        if full_relaxed:
            index.by_full_name_relaxed.setdefault(full_relaxed, []).append(u)
            # Also index by first-token + last-token so "Brandy L Brodie"
            # matches CSVs that just say "Brandy Brodie".
            parts = full_relaxed.split()
            if len(parts) >= 2:
                index.by_full_name_relaxed.setdefault(f"{parts[0]} {parts[-1]}", []).append(u)
        fn_relaxed = _relax(u.get("first_name") or "")
        ln_relaxed = _relax(u.get("last_name") or "")
        if fn_relaxed and ln_relaxed:
            index.by_first_last_relaxed.setdefault((fn_relaxed, ln_relaxed), []).append(u)
        # Also index by (first-word-of-first-name, last-name) for people
        # whose first_name field holds a compound like "Brandy L".
        if fn_relaxed:
            first_tok = fn_relaxed.split()[0]
            if first_tok and ln_relaxed:
                index.by_first_last_relaxed.setdefault((first_tok, ln_relaxed), []).append(u)

    # De-duplicate the relaxed lists (a user may key more than once).
    def _dedupe(m: dict):
        for k, lst in list(m.items()):
            seen: set[str] = set()
            unique: list[dict] = []
            for u in lst:
                if u.get("id") in seen:
                    continue
                seen.add(u.get("id"))
                unique.append(u)
            m[k] = unique
    _dedupe(index.by_full_name)
    _dedupe(index.by_first_last)
    _dedupe(index.by_full_name_relaxed)
    _dedupe(index.by_first_last_relaxed)

    return index


@dataclass
class MemberLookupResult:
    """Per-row outcome. Exactly one of `user` / `error` is populated."""
    user: Optional[dict] = None
    error: Optional[str] = None
    # The lookup-key the row used, useful for diagnostics ("email" / "full_name" / "first_last").
    matched_by: str = ""
    # Human-readable label for previews: email if used, else assembled name.
    label: str = ""


def resolve_member_for_row(row: dict, index: MemberLookupIndex) -> MemberLookupResult:
    """Resolve one CSV row's member using the pre-built `index`.

    `row` may have either original-case or already-lowered keys; we copy to
    lowered keys internally so callers don't have to think about it.

    Resolution priority: email → full_name → first_name+last_name. The first
    populated key decides the lookup; we don't silently fall through from
    a typo'd email to a name match (admin would never see the typo).

    Returns `MemberLookupResult` with either `user` set or `error` set.
    """
    r = {(k or "").strip().lower(): v for k, v in (row or {}).items() if k}

    email = _col(r, EMAIL_COLS)
    full = _col(r, FULL_NAME_COLS)
    fn = _col(r, FIRST_NAME_COLS)
    ln = _col(r, LAST_NAME_COLS)

    if email:
        u = index.by_email.get(email.lower())
        label = email
        if not u:
            return MemberLookupResult(error=f"no member with email '{email}'", matched_by="email", label=label)
        return MemberLookupResult(user=u, matched_by="email", label=label)

    if full:
        hits = index.by_full_name.get(full.lower(), [])
        label = full
        if not hits:
            # Punctuation/whitespace-relaxed fallback: catches "Brandy L. Brodie"
            # ↔ "Brandy Brodie" and "O’Neill" ↔ "O Neill" style mismatches.
            hits = index.by_full_name_relaxed.get(_relax(full), [])
        if not hits:
            return MemberLookupResult(error=f"no member named '{full}'", matched_by="full_name", label=label)
        if len(hits) > 1:
            return MemberLookupResult(
                error=(
                    f"ambiguous: {len(hits)} members named '{full}'. "
                    "Add a 'member_email' column to this row to disambiguate."
                ),
                matched_by="full_name",
                label=label,
            )
        return MemberLookupResult(user=hits[0], matched_by="full_name", label=label)

    if fn and ln:
        hits = index.by_first_last.get((fn.lower(), ln.lower()), [])
        label = f"{fn} {ln}"
        if not hits:
            hits = index.by_first_last_relaxed.get((_relax(fn), _relax(ln)), [])
        if not hits:
            return MemberLookupResult(error=f"no member named '{fn} {ln}'", matched_by="first_last", label=label)
        if len(hits) > 1:
            return MemberLookupResult(
                error=(
                    f"ambiguous: {len(hits)} members named '{fn} {ln}'. "
                    "Add a 'member_email' column to this row to disambiguate."
                ),
                matched_by="first_last",
                label=label,
            )
        return MemberLookupResult(user=hits[0], matched_by="first_last", label=label)

    return MemberLookupResult(
        error="row is missing a member identifier (need member_email, OR full_name, OR first_name+last_name)",
        matched_by="",
        label="",
    )
