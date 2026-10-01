"""Explicit bot provisioning, separate from request handling and calculations."""

import asyncio
import json
from urllib.parse import urlsplit

import httpx

from surveyor.config import settings
from surveyor.telegram import call_telegram

COMMANDS = [
    {"command": "start", "description": "Открыть Сюрвейер"},
    {"command": "help", "description": "Как работать с ботом"},
    {"command": "id", "description": "Мой Telegram ID для привязки учётной записи"},
]


async def set_menu(menu):
    # Telegram documents this parameter as a JSON-serialized MenuButton.
    return await call_telegram(
        "setChatMenuButton", data={"menu_button": json.dumps(menu, ensure_ascii=False)}
    )


async def verify_identity():
    if not settings.telegram_expected_bot_id:
        raise ValueError("Set TELEGRAM_EXPECTED_BOT_ID before configuring the bot")
    bot = await call_telegram("getMe")
    if str(bot["id"]) != settings.telegram_expected_bot_id:
        raise ValueError("Bot identity differs from TELEGRAM_EXPECTED_BOT_ID; nothing changed")
    return bot


async def configure_profile():
    bot = await verify_identity()
    await call_telegram("setMyCommands", json={"commands": COMMANDS})
    await call_telegram("setMyName", json={"name": "Сюрвейер · INSON"})
    await call_telegram(
        "setMyShortDescription",
        json={"short_description": "Осмотры, документы, расчёт страховой премии и сюрвейерские акты."},
    )
    await call_telegram(
        "setMyDescription",
        json={
            "description": "Рабочее пространство страхового специалиста: загрузите документы, проверьте данные и сформируйте акт. Для начала нажмите /start. Доступ — по учётной записи сотрудника."
        },
    )
    return bot


async def configure_webhook(*, replace_existing=False):
    url = urlsplit(settings.public_url)
    if url.scheme != "https" or not url.hostname or url.username or url.query or url.fragment:
        raise ValueError("A public HTTPS origin is required for Telegram")
    if not settings.telegram_webhook_secret:
        raise ValueError("TELEGRAM_WEBHOOK_SECRET is required")
    await verify_identity()
    target = settings.public_url.rstrip("/") + "/telegram/webhook"
    previous = await call_telegram("getWebhookInfo")
    if previous.get("url") not in {None, "", target} and not replace_existing:
        raise ValueError(
            "This bot already has another webhook. Use --replace-webhook to move it intentionally"
        )
    async with httpx.AsyncClient(timeout=15) as client:
        response = await client.get(settings.public_url.rstrip("/") + "/health")
        response.raise_for_status()
        if response.json().get("status") != "ok":
            raise ValueError("Public app health check failed; webhook unchanged")
    bot = await configure_profile()
    await call_telegram(
        "setWebhook",
        json={
            "url": target,
            "secret_token": settings.telegram_webhook_secret,
            "allowed_updates": ["message"],
        },
    )
    await set_menu({"type": "web_app", "text": "Открыть Сюрвейер", "web_app": {"url": settings.public_url}})
    # Telegram may briefly return cached menu settings after a successful write.
    for _ in range(40):
        info = await call_telegram("getWebhookInfo")
        menu = await call_telegram("getChatMenuButton")
        if info.get("url", "").rstrip("/") == target and menu.get("web_app", {}).get("url", "").rstrip(
            "/"
        ) == settings.public_url.rstrip("/"):
            return bot
        await asyncio.sleep(3)
    raise ValueError(
        f"Telegram read-back differs: webhook origin={urlsplit(info.get('url', '')).hostname}, menu type={menu.get('type')}, menu origin={urlsplit(menu.get('web_app', {}).get('url', '')).hostname}"
    )
