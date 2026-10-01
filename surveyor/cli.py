"""Operational entrypoints. Never print tokens or external request URLs."""

import argparse
import asyncio

from surveyor.config import settings
from surveyor.db import SessionLocal
from surveyor.sources import collect_cbu
from surveyor.telegram import call_telegram, handle_update


async def poll():
    info = await call_telegram("getWebhookInfo")
    if info.get("url"):
        raise SystemExit("Webhook already configured. Polling cannot start until that deployment is stopped.")
    print("Telegram polling started. Use /start or /id in the bot.")
    offset = 0
    while True:
        try:
            updates = await call_telegram(
                "getUpdates", json={"offset": offset, "timeout": 20, "allowed_updates": ["message"]}
            )
            for update in updates:
                with SessionLocal() as db:
                    await handle_update(update, db)
                offset = update["update_id"] + 1
        except Exception:
            print("Telegram request failed; retrying in 5 seconds (credentials redacted)")
            await asyncio.sleep(5)


async def configure():
    if not settings.public_url.startswith("https://") or not settings.telegram_webhook_secret:
        raise SystemExit("HTTPS PUBLIC_URL and TELEGRAM_WEBHOOK_SECRET are required")
    await call_telegram(
        "setWebhook",
        json={
            "url": settings.public_url.rstrip("/") + "/telegram/webhook",
            "secret_token": settings.telegram_webhook_secret,
            "allowed_updates": ["message"],
        },
    )
    await call_telegram(
        "setChatMenuButton",
        json={
            "menu_button": {"type": "web_app", "text": "Сюрвейер", "web_app": {"url": settings.public_url}}
        },
    )
    print("Telegram webhook and Mini App menu configured")


async def identity():
    result = await call_telegram("getMe")
    print(f"Telegram bot verified: @{result['username']}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "command", choices=["poll", "telegram-check", "telegram-configure", "collect", "worker"]
    )
    args = parser.parse_args()
    if args.command in {"poll", "telegram-check", "telegram-configure"}:
        asyncio.run(
            {"poll": poll, "telegram-check": identity, "telegram-configure": configure}[args.command]()
        )
    elif args.command == "collect":
        with SessionLocal() as db:
            print(collect_cbu(db))
    else:

        async def worker():
            while True:
                with SessionLocal() as db:
                    collect_cbu(db)
                await asyncio.sleep(3600)

        asyncio.run(worker())


if __name__ == "__main__":
    main()
