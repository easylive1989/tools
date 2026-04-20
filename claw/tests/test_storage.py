from pathlib import Path

import pytest

from claw.storage import Storage


@pytest.fixture
def store(tmp_path: Path) -> Storage:
    s = Storage(tmp_path / "claw.db")
    yield s
    s.close()


def test_record_message_is_idempotent(store: Storage) -> None:
    first = store.record_message("m1", "c1", None, "u1", "hello", 1000)
    second = store.record_message("m1", "c1", None, "u1", "hello", 1000)
    assert first is True
    assert second is False


def test_mark_processed(store: Storage) -> None:
    store.record_message("m1", "c1", None, "u1", "hello", 1000)
    assert store.is_processed("m1") is False
    store.mark_processed("m1")
    assert store.is_processed("m1") is True


def test_update_last_processed_id_only_advances(store: Storage) -> None:
    store.update_last_processed_id("c1", "100")
    assert store.get_last_processed_id("c1") == "100"

    store.update_last_processed_id("c1", "50")
    assert store.get_last_processed_id("c1") == "100"

    store.update_last_processed_id("c1", "200")
    assert store.get_last_processed_id("c1") == "200"


def test_thread_lifecycle(store: Storage) -> None:
    store.upsert_thread("t1", "m1", "gemini")
    t = store.get_thread("t1")
    assert t is not None
    assert t.parent_msg_id == "m1"
    assert t.cli_session_id is None
    assert t.cli_kind == "gemini"

    # upsert again keeps original
    store.upsert_thread("t1", "m1-other", "gemini")
    t = store.get_thread("t1")
    assert t.parent_msg_id == "m1"

    store.set_cli_session("t1", "sess-123", "gemini")
    assert store.get_thread("t1").cli_session_id == "sess-123"
    assert store.get_thread("t1").cli_kind == "gemini"

    # switching CLI: kind + session update together
    store.set_cli_session("t1", "claude-sess", "claude")
    t = store.get_thread("t1")
    assert t.cli_session_id == "claude-sess"
    assert t.cli_kind == "claude"


def test_last_message_id_in_thread(store: Storage) -> None:
    store.record_message("m1", "c1", "t1", "u1", "a", 100)
    store.record_message("m2", "c1", "t1", "u1", "b", 200)
    store.record_message("m3", "c1", "t1", "u1", "c", 150)
    assert store.last_message_id_in_thread("t1") == "m2"


def test_unprocessed_messages_ordered(store: Storage) -> None:
    store.record_message("m3", "c1", None, "u1", "c", 300)
    store.record_message("m1", "c1", None, "u1", "a", 100)
    store.record_message("m2", "c1", None, "u1", "b", 200)
    store.mark_processed("m1")

    ids = [m.message_id for m in store.unprocessed_messages()]
    assert ids == ["m2", "m3"]


def test_task_lifecycle(store: Storage) -> None:
    store.record_message("m1", "c1", None, "u1", "a", 100)
    store.start_task("m1")
    store.finish_task("m1")
    # start again -> still no error (idempotent-ish)
    store.start_task("m1")
    store.finish_task("m1", error="boom")
