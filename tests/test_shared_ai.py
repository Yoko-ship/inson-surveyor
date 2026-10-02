"""Real app authorization, persistence and worker tests; provider responses are fictional."""

from contextlib import ExitStack

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from surveyor import ai_config, ai_jobs, ai_providers, codex_documents
from surveyor.auth import hasher
from surveyor.config import settings
from surveyor.db import AIJob, ImportBatch, User
from tests.test_codex_telegram import owner, proof, upload  # noqa: F401


@pytest.fixture
def team(request):
    primary = request.getfixturevalue("owner")
    with ExitStack() as stack:
        members = []
        for index in range(2):
            telegram_id = str(222333440 + index)
            with primary.factory() as db:
                user = User(
                    login=f"shared-{index}",
                    phone=f"+99890000001{index}",
                    name=f"Fictional employee {index}",
                    role="employee",
                    telegram_id=telegram_id,
                    password_hash=hasher.hash("shared-test-password"),
                    must_change_password=False,
                )
                db.add(user)
                db.commit()
                user_id = user.id
            client = stack.enter_context(TestClient(primary.app, base_url=settings.public_url))
            response = client.post(
                "/api/auth/login", json={"login": f"shared-{index}", "password": "shared-test-password"}
            )
            assert response.status_code == 200
            client.headers["X-CSRF-Token"] = response.json()["csrf"]
            client.headers["X-Telegram-Init-Data"] = proof(telegram_id)
            client.factory, client.user_id = primary.factory, user_id
            members.append(client)
        yield members


def case(client):
    survey = client.post("/api/surveys", json={"title": "Fictional shared-access test"}).json()
    doc = client.post(
        f"/api/surveys/{survey['id']}/documents",
        files={"file": ("sample.txt", "Страховая сумма: 1000 UZS".encode())},
    ).json()
    body = {
        "revision": doc["revision"],
        "kind": "document",
        "document_ids": [doc["id"]],
        "cloud_consent": True,
        "config_revision": ai_config.digest(ai_config.load()),
        "locale": "ru",
    }
    return survey, doc, body


def extraction(*args, **kwargs):
    return {
        "fields": [
            {
                "field": "insured_sum",
                "value": "1000",
                "quote": "Страховая сумма: 1000 UZS",
                "status": "needs_review",
                "quote_found_in_text": True,
            }
        ],
        "summary": "Вымышленный документ: проверьте сумму.",
    }


@pytest.mark.parametrize("role", ["employee", "actuary", "underwriter", "admin"])
def test_linked_roles_use_existing_provider_without_admin_permissions(team, monkeypatch, role):
    employee = team[0]
    with employee.factory() as db:
        db.get(User, employee.user_id).role = role
        db.commit()
    monkeypatch.setattr(codex_documents, "recognize_document", extraction)
    status = employee.get("/api/ai-pilot")
    assert status.status_code == 200
    assert status.json()["provider"] == "codex"
    assert status.json()["telegram_access"] == "linked_users"
    assert "prompts" not in status.json()
    assert upload(employee).status_code == 200
    if role != "admin":
        assert employee.get("/api/admin/employees").status_code == 403


def test_owner_mode_can_be_restored_in_code(team, request):
    primary = request.getfixturevalue("owner")
    config = ai_config.load()
    config.telegram_access = "owner"
    ai_config.DEFAULT_PATH.write_text(config.model_dump_json())
    assert team[0].get("/api/ai-pilot").status_code == 403
    assert primary.get("/api/ai-pilot").status_code == 200


@pytest.mark.parametrize("change,expected", [("inactive", 401), ("unlinked", 403), ("password", 403)])
def test_shared_access_still_requires_active_linked_account(team, change, expected):
    employee = team[0]
    with employee.factory() as db:
        user = db.get(User, employee.user_id)
        if change == "inactive":
            user.active = False
        elif change == "unlinked":
            user.telegram_id = None
        else:
            user.must_change_password = True
        db.commit()
    assert employee.get("/api/ai-pilot").status_code == expected


def test_shared_queue_review_and_cross_user_isolation(team, request, monkeypatch):
    primary = request.getfixturevalue("owner")
    first, second = team
    monkeypatch.setattr(codex_documents, "recognize_document", extraction)
    survey, doc, body = case(first)
    url = f"/api/ai-pilot/surveys/{survey['id']}/jobs"
    job = first.post(url, json=body)
    assert job.status_code == 202, job.text
    job_id = job.json()["id"]
    assert first.post(url, json=body).json()["id"] == job_id
    for foreign in [second, primary]:
        assert foreign.get(url).status_code == 404
        assert foreign.post(url, json=body).status_code == 404
        assert foreign.get(f"/api/ai-pilot/jobs/{job_id}").status_code == 404
        assert foreign.post(f"/api/ai-pilot/jobs/{job_id}/cancel").status_code == 404
        assert foreign.get(f"/api/ai-pilot/documents/{doc['id']}/proposal").status_code == 404
    other_survey, other_doc, other_body = case(second)
    other_job = second.post(f"/api/ai-pilot/surveys/{other_survey['id']}/jobs", json=other_body)
    assert other_job.status_code == 202
    assert ai_jobs.process_one(first.factory)
    assert ai_jobs.process_one(first.factory)
    result = first.get(f"/api/ai-pilot/jobs/{job_id}").json()
    assert result["status"] == "completed", result
    assert second.get(f"/api/ai-pilot/jobs/{other_job.json()['id']}").json()["status"] == "completed"
    proposal_id = result["result"]["id"]
    review = {
        "revision": doc["revision"],
        "kind": "contract",
        "fields": {"insured_sum": "1000"},
        "reason": "Fictional source verified",
        "review_confirmed": True,
    }
    assert (
        second.post(
            f"/api/ai-pilot/documents/{doc['id']}/proposals/{proposal_id}/review", json=review
        ).status_code
        == 404
    )
    assert (
        second.post(
            f"/api/ai-pilot/documents/{other_doc['id']}/proposals/{proposal_id}/review", json=review
        ).status_code
        == 404
    )
    accepted = first.post(f"/api/ai-pilot/documents/{doc['id']}/proposals/{proposal_id}/review", json=review)
    assert accepted.status_code == 200, accepted.text
    assert accepted.json()["extracted"]["ai_reviews"][0]["reviewed_by"] == first.user_id


@pytest.mark.parametrize("during", [False, True])
@pytest.mark.parametrize("change", ["inactive", "relinked", "password", "owner_mode"])
def test_revoked_shared_access_stops_jobs_and_discards_proposals(team, monkeypatch, change, during):
    employee = team[0]
    survey, _, body = case(employee)
    job = employee.post(f"/api/ai-pilot/surveys/{survey['id']}/jobs", json=body).json()
    calls = []

    def revoke():
        with employee.factory() as db:
            user = db.get(User, employee.user_id)
            if change == "inactive":
                user.active = False
            elif change == "relinked":
                user.telegram_id = "999111222"
            elif change == "password":
                user.must_change_password = True
            db.commit()
        if change == "owner_mode":
            config = ai_config.load()
            config.telegram_access = "owner"
            ai_config.DEFAULT_PATH.write_text(config.model_dump_json())

    def generate(*args, **kwargs):
        calls.append(True)
        if during:
            revoke()
        return extraction()

    monkeypatch.setattr(codex_documents, "recognize_document", generate)
    if not during:
        revoke()
    assert ai_jobs.process_one(employee.factory)
    assert len(calls) == int(during)
    with employee.factory() as db:
        saved = db.get(AIJob, job["id"])
        assert saved.status == "failed" and saved.result == {}
        assert db.scalar(select(ImportBatch).where(ImportBatch.kind == "ai_document")) is None


def test_shared_inspection_comparison_preserves_owner_and_review(team, monkeypatch):
    employee, other = team
    survey, _, body = case(employee)

    def generate(config, instructions, content, images, directory, schema):
        return {"findings": [], "questions": ["Уточните условия."], "explanation": []}

    monkeypatch.setattr(ai_providers.PROVIDERS["codex"], "generate", generate)
    body["kind"] = "inspection"
    job = employee.post(f"/api/ai-pilot/surveys/{survey['id']}/jobs", json=body).json()
    assert ai_jobs.process_one(employee.factory)
    result = employee.get(f"/api/ai-pilot/jobs/{job['id']}").json()
    assert result["status"] == "completed", result
    review = {
        "revision": body["revision"],
        "accepted": {},
        "reason": "Checked fictional evidence",
        "review_confirmed": True,
    }
    url = f"/api/ai-pilot/jobs/{job['id']}/review"
    assert other.post(url, json=review).status_code == 404
    assert employee.post(url, json=review).status_code == 200


@pytest.mark.parametrize("stored", [False, True])
def test_revocation_during_synchronous_analysis_returns_no_result(team, monkeypatch, stored):
    employee = team[0]
    _, doc, body = case(employee)

    def generate(*args, **kwargs):
        with employee.factory() as db:
            db.get(User, employee.user_id).active = False
            db.commit()
        return extraction()

    monkeypatch.setattr(codex_documents, "recognize_document", generate)
    if stored:
        body = {key: value for key, value in body.items() if key not in {"kind", "document_ids"}}
        response = employee.post(f"/api/ai-pilot/documents/{doc['id']}/analyze", json=body)
    else:
        response = upload(employee)
    assert response.status_code == 403, response.text
    with employee.factory() as db:
        assert db.scalar(select(ImportBatch)) is None


def test_shared_access_rejects_anonymous_and_mismatched_telegram_identity(team):
    first, _ = team
    assert first.get("/api/ai-pilot", headers={"X-Telegram-Init-Data": proof("222333441")}).status_code == 403
    first.cookies.clear()
    assert first.get("/api/ai-pilot").status_code == 401
