"""Token service unit tests."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../backend"))

from services.token_service import issue_token, verify_token, _hash_token


def test_issue_token_returns_plaintext_and_id():
    plaintext, token_id = issue_token(label="test-issue")
    assert plaintext.startswith("sd_")
    assert len(plaintext) > 30
    assert isinstance(token_id, int)


def test_verify_token_returns_record_for_valid():
    plaintext, _ = issue_token(label="test-verify")
    rec = verify_token(plaintext)
    assert rec is not None
    assert rec["label"] == "test-verify"


def test_verify_token_returns_none_for_unknown():
    assert verify_token("sd_doesnotexist") is None
    assert verify_token("") is None
    assert verify_token(None) is None


def test_verify_token_returns_none_for_revoked():
    from repositories.api_tokens import revoke_token
    plaintext, token_id = issue_token(label="test-revoked")
    revoke_token(token_id)
    assert verify_token(plaintext) is None


def test_token_hash_is_deterministic():
    assert _hash_token("foo") == _hash_token("foo")
    assert _hash_token("foo") != _hash_token("bar")
    assert len(_hash_token("foo")) == 64


def test_issue_token_with_no_expiry():
    plaintext, _ = issue_token(label="no-expiry", expiry_days=None)
    rec = verify_token(plaintext)
    assert rec is not None
    assert rec["expires_at"] is None
