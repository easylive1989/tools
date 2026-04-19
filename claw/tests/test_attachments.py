from claw.attachments import build_attachment_prompt, sanitize_filename


def test_sanitize_strips_path_and_spaces() -> None:
    assert sanitize_filename("../../etc/passwd") == "passwd"
    assert sanitize_filename("my photo.png") == "my_photo.png"


def test_sanitize_keeps_extensions() -> None:
    assert sanitize_filename("resume.PDF") == "resume.PDF"
    assert sanitize_filename("CJK名稱.txt").endswith(".txt")


def test_sanitize_handles_empty() -> None:
    assert sanitize_filename("") == "file"
    assert sanitize_filename("!!!") == "file"


def test_sanitize_truncates_long_names() -> None:
    long_name = "a" * 500 + ".txt"
    sanitized = sanitize_filename(long_name)
    assert len(sanitized) <= 120


def test_build_prompt_no_attachments() -> None:
    assert build_attachment_prompt("hello", []) == "hello"


def test_build_prompt_appends_refs() -> None:
    result = build_attachment_prompt(
        "summarise this",
        ["attachments/123/report.pdf", "attachments/123/photo.png"],
    )
    assert result.startswith("summarise this")
    assert "@attachments/123/report.pdf" in result
    assert "@attachments/123/photo.png" in result


def test_build_prompt_only_refs_when_base_empty() -> None:
    result = build_attachment_prompt("", ["attachments/1/a.png"])
    assert result == "@attachments/1/a.png"


def test_build_prompt_whitespace_only_base_treated_empty() -> None:
    result = build_attachment_prompt("   \n  ", ["attachments/1/a.png"])
    assert result == "@attachments/1/a.png"
