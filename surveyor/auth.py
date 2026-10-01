import hashlib
import hmac
import json
import secrets
import time
from datetime import timedelta
from urllib.parse import parse_qsl

from argon2 import PasswordHasher
from argon2.exceptions import VerificationError
from fastapi import Depends, HTTPException, Request

from surveyor.config import settings
from surveyor.db import Session, User, get_db, now

hasher = PasswordHasher()
DUMMY_HASH = hasher.hash(secrets.token_urlsafe(32))


def verify_password(password, hashed):
    try:
        return hasher.verify(hashed, password)
    except VerificationError:
        return False


def digest(token):
    return hashlib.sha256(token.encode()).hexdigest()


def create_session(db, user, response):
    token = secrets.token_urlsafe(48)
    session = Session(
        token_hash=digest(token),
        user_id=user.id,
        csrf=secrets.token_urlsafe(32),
        expires_at=now() + timedelta(hours=settings.session_hours),
    )
    db.add(session)
    db.commit()
    response.set_cookie(
        "session",
        token,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        max_age=settings.session_hours * 3600,
    )
    return session


def current_user(request: Request, db=Depends(get_db)):
    token = request.cookies.get("session")
    session = db.get(Session, digest(token)) if token else None
    if not session or session.expires_at < now():
        raise HTTPException(401, "Войдите в систему")
    user = db.get(User, session.user_id)
    if not user or not user.active:
        raise HTTPException(401, "Учётная запись отключена")
    if request.method not in {"GET", "HEAD", "OPTIONS"}:
        if not secrets.compare_digest(request.headers.get("x-csrf-token", ""), session.csrf):
            raise HTTPException(403, "Недействительный CSRF-токен; обновите страницу")
    if user.must_change_password and request.url.path not in {
        "/api/auth/me",
        "/api/auth/password",
        "/api/auth/logout",
    }:
        raise HTTPException(403, "При первом входе необходимо сменить пароль")
    request.state.session = session
    return user


def roles(*allowed):
    def dependency(user=Depends(current_user)):
        if user.role not in allowed:
            raise HTTPException(403, "Недостаточно прав")
        return user

    return dependency


def user_data(user):
    return {
        k: getattr(user, k)
        for k in [
            "id",
            "login",
            "name",
            "phone",
            "position",
            "department",
            "branch",
            "role",
            "active",
            "telegram_id",
            "must_change_password",
        ]
    }


def validate_telegram(init_data, bot_token, timestamp=None):
    pairs = parse_qsl(init_data, keep_blank_values=True, strict_parsing=True)
    fields = dict(pairs)
    if len(pairs) != len(fields):
        raise ValueError("Повторяющиеся поля Telegram")
    supplied = fields.pop("hash", "")
    check = "\n".join(f"{k}={v}" for k, v in sorted(fields.items()))
    key = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    expected = hmac.new(key, check.encode(), hashlib.sha256).hexdigest()
    if not supplied or not hmac.compare_digest(supplied, expected):
        raise ValueError("Неверная подпись Telegram")
    age = (timestamp or time.time()) - int(fields.get("auth_date", 0))
    if age < -30 or age > 300:
        raise ValueError("Откройте мини-приложение заново: авторизация устарела")
    user = json.loads(fields.get("user", "{}"))
    if not isinstance(user.get("id"), int) or user["id"] <= 0:
        raise ValueError("Telegram user отсутствует")
    return str(user["id"])
