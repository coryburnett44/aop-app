"""Iteration 68 — CSV importers accept name in lieu of email.

Covers /api/hours/admin/csv and /api/donations/admin/csv. Both must accept:
  * member_email (preferred)
  * full_name
  * first_name + last_name

with deterministic resolution order, ambiguity errors, and missing-identifier
errors. Email column is no longer hard-required for either CSV.
"""
import io
import uuid

import pytest

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from routes._csv_member_lookup import (
    MemberLookupIndex,
    member_lookup_columns_present,
    resolve_member_for_row,
)


def test_member_lookup_columns_present_email():
    assert member_lookup_columns_present({"member_email", "amount"})
    assert member_lookup_columns_present({"email"})


def test_member_lookup_columns_present_full_name():
    assert member_lookup_columns_present({"full_name", "hours", "date"})


def test_member_lookup_columns_present_first_last():
    assert member_lookup_columns_present({"first_name", "last_name", "hours"})


def test_member_lookup_columns_missing_only_first():
    # First name alone is not enough.
    assert not member_lookup_columns_present({"first_name", "hours"})


def test_member_lookup_columns_missing_no_identifier():
    assert not member_lookup_columns_present({"amount", "date"})


def _build_index(users):
    idx = MemberLookupIndex()
    for u in users:
        em = (u.get("email") or "").lower().strip()
        if em:
            idx.by_email[em] = u
        full = (u.get("name") or "").lower().strip()
        if full:
            idx.by_full_name.setdefault(full, []).append(u)
        fn = (u.get("first_name") or "").lower().strip()
        ln = (u.get("last_name") or "").lower().strip()
        if fn and ln:
            idx.by_first_last.setdefault((fn, ln), []).append(u)
    return idx


def test_resolve_email_match():
    u = {"id": "u1", "email": "jane@example.com", "name": "Jane Doe"}
    idx = _build_index([u])
    res = resolve_member_for_row({"member_email": "jane@example.com"}, idx)
    assert res.user is u
    assert res.matched_by == "email"
    assert res.error is None


def test_resolve_email_case_insensitive():
    u = {"id": "u1", "email": "jane@example.com", "name": "Jane Doe"}
    idx = _build_index([u])
    res = resolve_member_for_row({"member_email": "JANE@Example.COM"}, idx)
    assert res.user is u


def test_resolve_email_typo_does_not_fallback_to_name():
    """Typo'd email must NOT silently fall through to full_name — that hides the typo."""
    u = {"id": "u1", "email": "jane@example.com", "name": "Jane Doe"}
    idx = _build_index([u])
    res = resolve_member_for_row(
        {"member_email": "wrong@example.com", "full_name": "Jane Doe"}, idx
    )
    assert res.user is None
    assert "no member with email" in res.error


def test_resolve_full_name_match():
    u = {"id": "u1", "email": "jane@example.com", "name": "Jane Doe"}
    idx = _build_index([u])
    res = resolve_member_for_row({"full_name": "Jane Doe"}, idx)
    assert res.user is u
    assert res.matched_by == "full_name"


def test_resolve_full_name_case_insensitive():
    u = {"id": "u1", "email": "jane@example.com", "name": "Jane Doe"}
    idx = _build_index([u])
    res = resolve_member_for_row({"full_name": "jane doe"}, idx)
    assert res.user is u


def test_resolve_full_name_ambiguous():
    u1 = {"id": "u1", "email": "a@example.com", "name": "John Smith"}
    u2 = {"id": "u2", "email": "b@example.com", "name": "John Smith"}
    idx = _build_index([u1, u2])
    res = resolve_member_for_row({"full_name": "John Smith"}, idx)
    assert res.user is None
    assert "ambiguous" in res.error
    assert "2 members" in res.error


def test_resolve_first_last_match():
    u = {"id": "u1", "email": "jane@example.com", "name": "Jane Doe",
         "first_name": "Jane", "last_name": "Doe"}
    idx = _build_index([u])
    res = resolve_member_for_row({"first_name": "jane", "last_name": "DOE"}, idx)
    assert res.user is u
    assert res.matched_by == "first_last"


def test_resolve_first_last_ambiguous():
    u1 = {"id": "u1", "email": "a@example.com", "name": "John Q Smith",
          "first_name": "John", "last_name": "Smith"}
    u2 = {"id": "u2", "email": "b@example.com", "name": "John R Smith",
          "first_name": "John", "last_name": "Smith"}
    idx = _build_index([u1, u2])
    res = resolve_member_for_row({"first_name": "John", "last_name": "Smith"}, idx)
    assert res.user is None
    assert "ambiguous" in res.error


def test_resolve_missing_identifier():
    idx = _build_index([])
    res = resolve_member_for_row({"hours": "2.5", "date": "2026-06-15"}, idx)
    assert res.user is None
    assert "missing a member identifier" in res.error


def test_resolve_priority_email_over_name():
    """When both email and full_name are present, email wins."""
    u1 = {"id": "u1", "email": "primary@example.com", "name": "Same Name"}
    u2 = {"id": "u2", "email": "other@example.com", "name": "Same Name"}
    idx = _build_index([u1, u2])
    res = resolve_member_for_row(
        {"member_email": "primary@example.com", "full_name": "Same Name"}, idx
    )
    # Email path wins → no ambiguity error, user u1 returned.
    assert res.user is u1
    assert res.matched_by == "email"


def test_resolve_priority_full_name_over_first_last():
    u1 = {"id": "u1", "email": "a@example.com", "name": "Jane Doe",
          "first_name": "Jane", "last_name": "Doe"}
    u2 = {"id": "u2", "email": "b@example.com", "name": "Jane Doe",
          "first_name": "Jane", "last_name": "Doe"}
    idx = _build_index([u1, u2])
    # full_name is ambiguous; first_last would also be ambiguous. full_name path runs first.
    res = resolve_member_for_row(
        {"full_name": "Jane Doe", "first_name": "Jane", "last_name": "Doe"}, idx
    )
    assert res.matched_by == "full_name"
    assert res.error is not None
