"""Operational entrypoints. Never print tokens or external request URLs."""

import argparse
import asyncio

from surveyor.db import SessionLocal
from surveyor.sources import collect_all
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
    from surveyor.telegram_setup import configure_webhook

    bot = await configure_webhook()
    print(f"Telegram webhook and Mini App menu configured: @{bot['username']}")


async def identity():
    result = await call_telegram("getMe")
    print(f"Telegram bot verified: @{result['username']}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "command",
        choices=["poll", "telegram-check", "telegram-profile", "telegram-configure", "collect", "worker"],
    )
    parser.add_argument(
        "--replace-webhook", action="store_true", help="Intentionally move the pinned bot to PUBLIC_URL"
    )
    args = parser.parse_args()
    if args.command == "telegram-profile":
        from surveyor.telegram_setup import configure_profile

        bot = asyncio.run(configure_profile())
        print(f"Bot profile and commands configured: @{bot['username']}")
    elif args.command == "telegram-configure" and args.replace_webhook:
        from surveyor.telegram_setup import configure_webhook

        bot = asyncio.run(configure_webhook(replace_existing=True))
        print(f"Telegram webhook and Mini App menu configured: @{bot['username']}")
    elif args.command in {"poll", "telegram-check", "telegram-configure"}:
        asyncio.run(
            {"poll": poll, "telegram-check": identity, "telegram-configure": configure}[args.command]()
        )
    elif args.command == "collect":
        with SessionLocal() as db:
            print(collect_all(db))
    else:

        async def worker():
            from surveyor.worker import run_cycle

            while True:
                run_cycle()
                await asyncio.sleep(3600)

        asyncio.run(worker())


if __name__ == "__main__":
    main()
