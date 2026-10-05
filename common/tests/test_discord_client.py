from unittest.mock import MagicMock, Mock, patch

import pytest

from common.discord import DiscordClient


def fake_response(payload=None, status=200):
    response = Mock(status_code=status)
    response.json.return_value = payload
    return response


def test_messages_since_returns_only_newer_messages_oldest_first():
    client = DiscordClient("token")
    client.session.request = Mock(return_value=fake_response([
        {"id": "105"}, {"id": "104"}, {"id": "100"}, {"id": "99"},
    ]))
    assert [message["id"] for message in client.messages_since("1", "100")] == ["104", "105"]


def test_request_waits_out_rate_limits():
    client = DiscordClient("token")
    client.session.request = Mock(side_effect=[
        fake_response({"retry_after": 0.5}, status=429),
        fake_response([{"id": "7"}]),
    ])
    with patch("common.discord.time.sleep") as sleep:
        assert client.latest_message_id("1") == "7"
    sleep.assert_called_once_with(0.5)


def test_reply_quotes_the_original_without_pinging_anyone():
    client = DiscordClient("token")
    client.session.request = Mock(return_value=fake_response({"id": "900"}))
    assert client.reply("1", "100", "找不到") == "900"
    body = client.session.request.call_args.kwargs["json"]
    assert body["content"] == "找不到"
    assert body["message_reference"]["message_id"] == "100"
    assert body["allowed_mentions"] == {"parse": [], "replied_user": False}


def test_download_rejects_non_discord_hosts(tmp_path):
    with pytest.raises(ValueError, match="網址不正確"):
        DiscordClient("token").download("https://evil.example/a.png", tmp_path / "a.png")


def test_download_saves_attachment_without_the_bot_token(tmp_path):
    response = MagicMock()
    response.__enter__.return_value = response
    response.iter_content.return_value = [b"abc", b"def"]
    with patch("common.discord.requests.get", return_value=response) as get:
        path = DiscordClient("token").download(
            "https://cdn.discordapp.com/attachments/1/2/a.png", tmp_path / "a.png")
    assert path.read_bytes() == b"abcdef"
    assert "headers" not in get.call_args.kwargs
