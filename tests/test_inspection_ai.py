from pathlib import Path

import pytest
from sqlalchemy import select

from surveyor import ai_config, codex_documents, codex_pilot
from surveyor.db import Audit, Document, ImportBatch, Survey
from tests.test_codex_telegram import owner  # noqa: F401


@pytest.fixture
def workflow(request, monkeypatch):
    client = request.getfixturevalue("owner")
    survey = client.post("/api/surveys", json={"title": "AI review"}).json()
    doc = client.post(
        f"/api/surveys/{survey['id']}/documents",
        files={"file": ("contract.txt", "Страховая сумма: 1000 UZS".encode())},
    ).json()
    calls = []

    def recognize(data, filename, **kwargs):
        calls.append((data, filename, kwargs))
        return {
            "fields": [
                {
                    "field": "insured_sum",
                    "value": "1000",
                    "quote": "Страховая сумма: 1000 UZS",
                    "status": "needs_review",
                    "quote_found_in_text": True,
                },
                {
                    "field": "object_value",
                    "value": "2000",
                    "quote": "Стоимость: 2000 UZS",
                    "status": "needs_review",
                    "quote_found_in_text": False,
                },
                {
                    "field": "declared_rate",
                    "value": None,
                    "quote": "",
                    "status": "rejected",
                    "quote_found_in_text": False,
                },
            ],
            "summary": "**Review** these values",
        }

    monkeypatch.setattr(codex_documents, "recognize_document", recognize)
    return client, survey, doc, calls


def analyze(w, **changes):
    client, _, doc, _ = w
    return client.post(
        f"/api/ai-pilot/documents/{doc['id']}/analyze",
        json={
            "revision": doc["revision"],
            "cloud_consent": True,
            "config_revision": ai_config.digest(ai_config.load()),
            **changes,
        },
    )


def review(w, proposal, **changes):
    client, _, doc, _ = w
    return client.post(
        f"/api/ai-pilot/documents/{doc['id']}/proposals/{proposal['id']}/review",
        json={
            "revision": doc["revision"],
            "kind": "contract",
            "fields": {"insured_sum": "1000", "object_value": "2100"},
            "reason": "Compared with original",
            "review_confirmed": True,
            **changes,
        },
    )


def test_proposal_review_saved_inspection_and_immutable_exports(workflow):
    client, survey, doc, calls = workflow
    result = analyze(workflow)
    assert result.status_code == 200, result.text
    proposal = result.json()
    assert len(calls) == 1
    assert client.get(f"/api/ai-pilot/documents/{doc['id']}/proposal").json() == proposal
    before = client.get(f"/api/surveys/{survey['id']}").json()
    assert before["documents"][0]["extracted"] == doc["extracted"]
    assert before["revision"] == doc["revision"]
    assert client.post(f"/api/surveys/{survey['id']}/reports").status_code == 422
    result = review(workflow, proposal)
    assert result.status_code == 200, result.text
    evidence = result.json()["extracted"]["ai_reviews"][0]
    assert [r["decision"] for r in evidence["fields"]] == ["accepted", "corrected", "rejected"]
    assert evidence["fields"][1]["value"] == "2000"
    assert evidence["fields"][1]["reviewed_value"] == "2100"
    assert evidence["fields"][0]["quote"] == proposal["fields"][0]["quote"]
    assert evidence["config_revision"] == proposal["config_revision"]
    assert evidence["reviewer_name"] and evidence["reviewed_at"]
    assert client.get(f"/api/ai-pilot/documents/{doc['id']}/proposal").json() is None
    assert review(workflow, proposal).status_code == 409
    assert client.post(f"/api/surveys/{survey['id']}/reports").status_code == 422
    saved = client.put(
        f"/api/surveys/{survey['id']}",
        json={
            "revision": result.json()["revision"],
            "product_code": "DEMO-FIX",
            "insured_sum": "1000",
            "object_value": "2100",
            "region": "1726",
            "manual_review_confirmed": True,
            "language": "en",
        },
    )
    assert saved.status_code == 200, saved.text
    report = client.post(f"/api/surveys/{survey['id']}/reports").json()
    detail = client.get(f"/api/reports/{report['id']}").json()
    assert detail["snapshot"]["documents"][0]["extracted"]["ai_reviews"] == [evidence]
    lines = "\n".join(detail["sections"][0]["lines"])
    assert "AI proposal review" in lines and "Corrected: 2000 → 2100" in lines
    assert proposal["config_revision"] in lines and proposal["fields"][0]["quote"] in lines
    for format in ("docx", "pdf"):
        assert client.get(f"/api/reports/{report['id']}/export/{format}").status_code == 200
    with client.factory() as db:
        document = db.get(Document, doc["id"])
        document.extracted = {**document.extracted, "ai_reviews": []}
        db.commit()
    assert client.get(f"/api/reports/{report['id']}").json()["snapshot"] == detail["snapshot"]


def test_consent_config_auth_and_revision_before_inference(workflow):
    client, _, doc, calls = workflow
    assert analyze(workflow, cloud_consent=False).status_code == 422
    assert analyze(workflow, config_revision="outdated").status_code == 409
    assert analyze(workflow, revision=doc["revision"] + 1).status_code == 409
    client.headers.pop("X-Telegram-Init-Data")
    assert analyze(workflow).status_code == 403
    assert client.get(f"/api/ai-pilot/documents/{doc['id']}/proposal").status_code == 403
    assert not calls


def test_stale_proposal_invalidates_review_and_report_confirmation(workflow):
    client, survey, doc, _ = workflow
    proposal = analyze(workflow).json()
    client.put(
        f"/api/documents/{doc['id']}/review",
        json={
            "revision": doc["revision"],
            "kind": "contract",
            "fields": {"insured_sum": "1500"},
            "reason": "Manual correction",
        },
    )
    assert client.get(f"/api/ai-pilot/documents/{doc['id']}/proposal").json()["stale"]
    assert review(workflow, proposal).status_code == 409
    assert review(workflow, proposal, revision=doc["revision"] + 1).status_code == 409
    assert (
        client.get(f"/api/surveys/{survey['id']}").json()["documents"][0]["extracted"]["fields"][
            "insured_sum"
        ]["value"]
        == "1500"
    )


def test_invalid_review_rolls_back_consumption_and_reject_all(workflow):
    client, _, doc, _ = workflow
    proposal = analyze(workflow).json()
    assert review(workflow, proposal, review_confirmed=False).status_code == 422
    assert review(workflow, proposal, fields={"provider": "fake"}).status_code == 422
    assert review(workflow, proposal, fields={"insured_sum": "-1"}).status_code == 422
    assert client.get(f"/api/ai-pilot/documents/{doc['id']}/proposal").json()["id"] == proposal["id"]
    response = review(workflow, proposal, fields={})
    assert response.status_code == 200
    assert response.json()["extracted"]["fields"] == doc["extracted"]["fields"]
    assert all(r["decision"] == "rejected" for r in response.json()["extracted"]["ai_reviews"][0]["fields"])


def test_proposals_cannot_be_imported_or_applied_to_another_document(workflow):
    client, survey, _, _ = workflow
    proposal = analyze(workflow).json()
    assert client.post(f"/api/admin/imports/{proposal['id']}/confirm").status_code == 404
    assert client.post(f"/api/admin/source-imports/{proposal['id']}/confirm").status_code == 404
    other = client.post(
        f"/api/surveys/{survey['id']}/documents", files={"file": ("other.txt", b"other")}
    ).json()
    w = (client, survey, other, [])
    assert review(w, proposal).status_code == 404
    with client.factory() as db:
        db.get(Survey, survey["id"]).owner_id = "someone-else"
        db.commit()
    assert analyze(workflow).status_code == 404


def test_change_during_generation_leaves_no_proposal(workflow, monkeypatch):
    client, survey, _, _ = workflow
    original = codex_documents.recognize_document

    def changed(*args, **kwargs):
        with client.factory() as db:
            db.get(Survey, survey["id"]).revision += 1
            db.commit()
        return original(*args, **kwargs)

    monkeypatch.setattr(codex_documents, "recognize_document", changed)
    assert analyze(workflow).status_code == 409
    with client.factory() as db:
        assert db.scalar(select(ImportBatch)) is None
        assert db.scalar(select(Audit).where(Audit.action == "ai.document_proposed")) is None


def test_provider_failure_can_be_retried_without_partial_mutations(workflow, monkeypatch):
    client, _, _, calls = workflow
    original = codex_documents.recognize_document

    def failed(*args, **kwargs):
        raise codex_pilot.PilotError("Provider unavailable")

    monkeypatch.setattr(codex_documents, "recognize_document", failed)
    assert analyze(workflow).status_code == 503
    with client.factory() as db:
        assert db.scalar(select(ImportBatch)) is None
    monkeypatch.setattr(codex_documents, "recognize_document", original)
    assert analyze(workflow).status_code == 200
    assert len(calls) == 1


def test_pending_proposal_does_not_change_confirmed_inputs_or_report(workflow):
    client, survey, doc, _ = workflow
    saved = client.put(
        f"/api/surveys/{survey['id']}",
        json={
            "revision": doc["revision"],
            "product_code": "DEMO-FIX",
            "insured_sum": "1000",
            "object_value": "9000",
            "region": "1726",
            "manual_review_confirmed": True,
        },
    )
    assert saved.status_code == 200
    doc["revision"] += 1
    proposal = analyze(workflow).json()
    report = client.post(f"/api/surveys/{survey['id']}/reports").json()
    snapshot = client.get(f"/api/reports/{report['id']}").json()["snapshot"]
    assert snapshot["inputs"]["object_value"] == "9000"
    assert "ai_reviews" not in snapshot["documents"][0]["extracted"]
    assert review(workflow, proposal).status_code == 200
    assert client.post(f"/api/surveys/{survey['id']}/reports").status_code == 422
    inputs = client.get(f"/api/surveys/{survey['id']}").json()["inputs"]
    assert inputs["object_value"] == "9000" and not inputs["manual_review_confirmed"]


def test_tampered_file_cannot_be_analyzed_or_reviewed(workflow):
    client, _, doc, calls = workflow
    proposal = analyze(workflow).json()
    with client.factory() as db:
        Path(db.get(Document, doc["id"]).path).write_bytes(b"changed")
    assert analyze(workflow).status_code == 409
    assert review(workflow, proposal).status_code == 409
    assert len(calls) == 1
