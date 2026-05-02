"""Repository tests for api_tokens table."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../backend"))

from datetime import datetime, timedelta, timezone

from repositories.api_tokens import (
    insert_token, find_active_by_hash, touch_last_used,
    list_tokens, revoke_token,
)


def test_insert_and_find_token():
    token_id = insert_token("hash_abc", "sd_aaa", "label-a")
    assert isinstance(token_id, int)

    row = find_active_by_hash("hash_abc")
    assert row is not None
    assert row["id"] == token_id
    assert row["prefix"] == "sd_aaa"
    assert row["label"] == "label-a"
    assert row["revoked_at"] is None


def test_revoke_token_makes_it_inactive():
    token_id = insert_token("hash_revoked", "sd_rev", "to-revoke")
    assert revoke_token(token_id) is True

    row = find_active_by_hash("hash_revoked")
    assert row is None

    # Re-revoking returns False (already revoked)
    assert revoke_token(token_id) is False


def test_expired_token_not_returned_by_find_active():
    past = (datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=1)).isoformat()
    insert_token("hash_expired", "sd_exp", "expired-token", expires_at=past)

    assert find_active_by_hash("hash_expired") is None


def test_touch_last_used_updates_timestamp():
    token_id = insert_token("hash_touch", "sd_tou", "touch-test")
    row_before = find_active_by_hash("hash_touch")
    assert row_before["last_used_at"] is None

    touch_last_used(token_id)

    row_after = find_active_by_hash("hash_touch")
    assert row_after["last_used_at"] is not None


def test_list_tokens_returns_all_including_revoked():
    insert_token("hash_l1", "sd_l1a", "list-1")
    rid = insert_token("hash_l2", "sd_l2a", "list-2")
    revoke_token(rid)

    rows = list_tokens()
    labels = {r["label"] for r in rows}
    assert "list-1" in labels
    assert "list-2" in labels
