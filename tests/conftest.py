import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from surveyor import ai_config
from surveyor import bootstrap as boot
from surveyor.auth import hasher
from surveyor.config import settings
from surveyor.db import Base, User, get_db
from surveyor.main import app


@pytest.fixture(autouse=True)
def isolated_ai_config(tmp_path, monkeypatch):
    path = tmp_path / "ai-config.json"
    path.write_bytes(ai_config.DEFAULT_PATH.read_bytes())
    monkeypatch.setattr(ai_config, "DEFAULT_PATH", path)


@pytest.fixture
def client(tmp_path, monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    factory = sessionmaker(engine, expire_on_commit=False)
    Base.metadata.create_all(engine)
    monkeypatch.setattr(boot, "SessionLocal", factory)
    monkeypatch.setattr(settings, "bootstrap_admin_password", "initial-test-password")
    monkeypatch.setattr(settings, "storage_dir", tmp_path)
    monkeypatch.setattr(settings, "data_mode", "synthetic")
    monkeypatch.setattr(settings, "public_url", "http://testserver")
    monkeypatch.setattr(settings, "cookie_secure", False)
    monkeypatch.setattr(settings, "codex_telegram_enabled", False)

    def override():
        with factory() as db:
            yield db

    app.dependency_overrides[get_db] = override
    with TestClient(app) as c:
        c.factory = factory
        yield c
    app.dependency_overrides.clear()
    engine.dispose()


@pytest.fixture
def admin(client):
    response = client.post("/api/auth/login", json={"login": "admin", "password": "initial-test-password"})
    assert response.status_code == 200, response.text
    client.headers["X-CSRF-Token"] = response.json()["csrf"]
    response = client.post(
        "/api/auth/password",
        json={"old_password": "initial-test-password", "new_password": "changed-test-password"},
    )
    assert response.status_code == 200
    client.headers["X-CSRF-Token"] = response.json()["csrf"]
    return client


def switch_user(client, role="employee", login="employee"):
    with client.factory() as db:
        db.add(
            User(
                login=login,
                phone=f"+99890{len(db.query(User).all()):07}",
                name=login,
                role=role,
                password_hash=hasher.hash("password-test"),
                must_change_password=False,
            )
        )
        db.commit()
    response = client.post("/api/auth/login", json={"login": login, "password": "password-test"})
    assert response.status_code == 200
    client.headers["X-CSRF-Token"] = response.json()["csrf"]
    return response.json()["user"]
