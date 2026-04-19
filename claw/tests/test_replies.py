from claw.replies import split_for_discord


def test_short_text_not_split() -> None:
    assert split_for_discord("hello") == ["hello"]


def test_split_by_paragraph() -> None:
    p1 = "a" * 500
    p2 = "b" * 500
    p3 = "c" * 500
    p4 = "d" * 500
    text = "\n\n".join([p1, p2, p3, p4])
    chunks = split_for_discord(text, chunk_size=1100)
    assert all(len(c) <= 1100 for c in chunks)
    assert "".join(c.replace("\n\n", "") for c in chunks).count("a") == 500


def test_hard_cut_on_single_long_line() -> None:
    text = "x" * 5000
    chunks = split_for_discord(text, chunk_size=1000)
    assert all(len(c) <= 1000 for c in chunks)
    assert "".join(chunks) == text
