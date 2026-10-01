import hmac

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select

from surveyor.config import settings
from surveyor.db import TelegramUpdate, User, get_db

router = APIRouter()


async def call_telegram(method, **kwargs):
    if not settings.telegram_bot_token:
        raise HTTPException(503, "Telegram не настроен")
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(
                f"https://api.telegram.org/bot{settings.telegram_bot_token}/{method}", **kwargs
            )
        data = response.json()
        if not data.get("ok"):
            raise HTTPException(502, "Telegram не принял запрос. Проверьте токен и нажмите /start в боте")
        return data["result"]
    except (httpx.HTTPError, ValueError):
        raise HTTPException(502, "Telegram временно недоступен") from None


async def handle_update(update, db):
    update_id = update.get("update_id")
    if not isinstance(update_id, int):
        return
    if db.get(TelegramUpdate, update_id):
        return
    message = update.get("message", {})
    chat = message.get("chat", {})
    if chat.get("type") != "private":
        db.add(TelegramUpdate(update_id=update_id))
        db.commit()
        return
    chat_id = str(chat.get("id", ""))
    user = db.scalar(select(User).where(User.telegram_id == chat_id, User.active.is_(True)))
    text = message.get("text", "")
    if text.startswith(("/start", "/help")):
        reply = "Сюрвейер · осмотр, проверка документов, расчёт и акт.\nИИ отключён.\n"
        reply += f"Ваш Telegram ID: {chat_id}. "
        reply += (
            "Откройте приложение для работы."
            if user
            else "Войдите в приложение с учётной записью сотрудника и привяжите Telegram в профиле."
        )
        keyboard = (
            {"inline_keyboard": [[{"text": "Открыть Сюрвейер", "web_app": {"url": settings.public_url}}]]}
            if settings.public_url.startswith("https://")
            else None
        )
        payload = {"chat_id": chat_id, "text": reply}
        if keyboard:
            payload["reply_markup"] = keyboard
        await call_telegram("sendMessage", json=payload)
    elif text.startswith("/id"):
        await call_telegram("sendMessage", json={"chat_id": chat_id, "text": f"Telegram ID: {chat_id}"})
    db.add(TelegramUpdate(update_id=update_id))
    db.commit()


@router.post("/telegram/webhook")
async def webhook(request: Request, db=Depends(get_db)):
    provided = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
    if not settings.telegram_webhook_secret or not hmac.compare_digest(
        provided, settings.telegram_webhook_secret
    ):
        raise HTTPException(403, "Invalid webhook secret")
    await handle_update(await request.json(), db)
    return {"ok": True}
