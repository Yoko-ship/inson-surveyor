import asyncio
import json
from unittest.mock import AsyncMock

import httpx
import pytest

from surveyor.config import Settings, settings
from surveyor.telegram_setup import configure_profile, configure_webhook


def setup_api(monkeypatch, *, bot_id=123456, previous="", healthy=True):
    calls = []
    target = "https://surveyor.example"
    monkeypatch.setattr(settings, "telegram_expected_bot_id", "123456")
    monkeypatch.setattr(settings, "telegram_webhook_secret", "test-secret")
    monkeypatch.setattr(settings, "public_url", target)
    webhook = previous

    async def fake(method, **kwargs):
        nonlocal webhook
        calls.append(method)
        if method == "getMe":
            return {"id": bot_id, "username": "example_bot"}
        if method == "getWebhookInfo":
            return {"url": webhook}
        if method == "setWebhook":
            webhook = kwargs["json"]["url"]
        if method == "setChatMenuButton":
            assert json.loads(kwargs["data"]["menu_button"])["web_app"]["url"] == target
        if method == "getChatMenuButton":
            return {"type": "web_app", "web_app": {"url": target + "/"}}
        return True

    class Client:
        def __init__(self, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def get(self, url):
            return httpx.Response(
                200 if healthy else 503, json={"status": "ok"}, request=httpx.Request("GET", url)
            )

    monkeypatch.setattr("surveyor.telegram_setup.call_telegram", fake)
    monkeypatch.setattr("surveyor.telegram_setup.httpx.AsyncClient", Client)
    return calls


def test_wrong_bot_is_never_modified(monkeypatch):
    calls = setup_api(monkeypatch, bot_id=999)
    with pytest.raises(ValueError, match="identity"):
        asyncio.run(configure_profile())
    assert calls == ["getMe"]


def test_existing_webhook_needs_explicit_move(monkeypatch):
    calls = setup_api(monkeypatch, previous="https://previous.example/telegram/webhook")
    with pytest.raises(ValueError, match="already has another"):
        asyncio.run(configure_webhook())
    assert not any(method.startswith("set") for method in calls)


def test_unhealthy_app_does_not_change_bot(monkeypatch):
    calls = setup_api(monkeypatch, healthy=False)
    with pytest.raises(httpx.HTTPStatusError):
        asyncio.run(configure_webhook())
    assert not any(method.startswith("set") for method in calls)


def test_setup_reads_back_webhook_and_menu(monkeypatch):
    calls = setup_api(monkeypatch)
    assert asyncio.run(configure_webhook())["username"] == "example_bot"
    assert "setMyCommands" in calls
    assert calls[-2:] == ["getWebhookInfo", "getChatMenuButton"]


def test_menu_cache_can_take_multiple_reads_to_update(monkeypatch):
    from surveyor import telegram_setup

    setup_api(monkeypatch)
    fake = telegram_setup.call_telegram
    menu_reads = 0

    async def delayed_menu(method, **kwargs):
        nonlocal menu_reads
        result = await fake(method, **kwargs)
        if method == "getChatMenuButton":
            menu_reads += 1
            if menu_reads <= 6:
                return {"type": "commands"}
        return result

    monkeypatch.setattr(telegram_setup, "call_telegram", delayed_menu)
    monkeypatch.setattr(telegram_setup.asyncio, "sleep", AsyncMock())
    assert asyncio.run(configure_webhook())["username"] == "example_bot"
    assert menu_reads == 7


def test_telegram_cookie_requires_https():
    with pytest.raises(ValueError, match="SameSite=None"):
        Settings(_env_file=None, cookie_samesite="none", cookie_secure=False)


def test_secure_cookie_for_telegram_iframe(client, monkeypatch):
    monkeypatch.setattr(settings, "cookie_secure", True)
    monkeypatch.setattr(settings, "cookie_samesite", "none")
    response = client.post("/api/auth/login", json={"login": "admin", "password": "initial-test-password"})
    assert response.status_code == 200
    cookie = response.headers["set-cookie"].lower()
    assert "secure" in cookie and "httponly" in cookie and "samesite=none" in cookie


def test_profile_setup_skips_unchanged_name(monkeypatch):
    import asyncio

    from surveyor import telegram_setup
    from surveyor.config import settings

    calls = []
    monkeypatch.setattr(settings, "telegram_expected_bot_id", "12345")

    async def fake(method, **kwargs):
        calls.append(method)
        if method == "getMe":
            return {"id": 12345, "username": "test_bot"}
        if method == "getMyCommands":
            return telegram_setup.COMMANDS
        if method == "getMyName":
            return {"name": "Сюрвейер · INSON"}
        if method == "setMyName":
            raise AssertionError("Unchanged name must not be written")
        return {}

    monkeypatch.setattr(telegram_setup, "call_telegram", fake)
    assert asyncio.run(telegram_setup.configure_profile())["id"] == 12345
    assert "setMyCommands" not in calls and "setMyName" not in calls
