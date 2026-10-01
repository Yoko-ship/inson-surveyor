import hashlib
import hmac
import io
import json
from datetime import date
from urllib.parse import urlencode

import pytest
from conftest import switch_user
from docx import Document as Docx
from pypdf import PdfReader

from surveyor.auth import validate_telegram
from surveyor.db import Audit, Product
from surveyor.documents import parse_document


def body(**kw):
    return {
        "revision": 1,
        "product_code": "DEMO-FIX",
        "insured_sum": "100000000",
        "object_value": "100000000",
        "region": "Ташкент",
        "term_days": 1095,
        "tariff_date": date.today().isoformat(),
        "manual_review_confirmed": True,
        **kw,
    }


def survey(client):
    response = client.post("/api/surveys", json={"title": "Учебный объект"})
    assert response.status_code == 201, response.text
    return response.json()["id"]


def test_first_login_forces_password_change(client):
    response = client.post("/api/auth/login", json={"login": "admin", "password": "initial-test-password"})
    assert response.status_code == 200
    assert response.json()["user"]["must_change_password"]
    assert client.get("/api/surveys").status_code == 403


def test_csrf_and_origin(admin):
    assert (
        admin.post("/api/surveys", json={"title": "test"}, headers={"X-CSRF-Token": "invalid"}).status_code
        == 403
    )
    assert (
        admin.post(
            "/api/surveys", json={"title": "test"}, headers={"Origin": "https://evil.example"}
        ).status_code
        == 403
    )


def test_report_pdf_word_and_snapshot_immutability(admin):
    sid = survey(admin)
    update = admin.put(f"/api/surveys/{sid}", json=body())
    assert update.status_code == 200, update.text
    response = admin.post(f"/api/surveys/{sid}/reports")
    assert response.status_code == 201, response.text
    rid = response.json()["id"]
    assert response.json()["snapshot"]["calculation"]["premium"] == "500000.00"
    pdf = admin.get(f"/api/reports/{rid}/export/pdf")
    assert pdf.status_code == 200, pdf.text[:200] if pdf.status_code != 200 else ""
    text = "\n".join(p.extract_text() for p in PdfReader(io.BytesIO(pdf.content)).pages)
    assert "Сюрвейерский акт" in text
    assert "500000.00" in text
    word = admin.get(f"/api/reports/{rid}/export/docx")
    assert word.status_code == 200
    doc = Docx(io.BytesIO(word.content))
    assert len([p for p in doc.paragraphs if p.style.name == "Heading 1"]) == 5
    assert admin.put(f"/api/surveys/{sid}", json=body(revision=2, insured_sum="200000000")).status_code == 200
    assert admin.get(f"/api/reports/{rid}").json()["snapshot"]["calculation"]["premium"] == "500000.00"


def test_stale_revision_rejected(admin):
    sid = survey(admin)
    assert admin.put(f"/api/surveys/{sid}", json=body()).status_code == 200
    assert admin.put(f"/api/surveys/{sid}", json=body()).status_code == 409
    with admin.factory() as db:
        entry = db.query(Audit).filter_by(action="survey.inputs_changed").first()
        assert entry.data["before"] == {}
        assert entry.data["after"]["insured_sum"] == "100000000"


def test_employee_cannot_read_other_survey_or_admin(admin):
    sid = survey(admin)
    switch_user(admin)
    assert admin.get(f"/api/surveys/{sid}").status_code == 404
    assert admin.get("/api/admin/employees").status_code == 403
    assert admin.get("/api/surveys").json() == []


def test_import_preview_atomic_confirm_and_replay(admin):
    data = "code,name,class_code,rate,min_rate,rate_type,effective_from\nP1,Test,property,0.5,0.3,fixed,2026-01-01\n"
    result = admin.post("/api/admin/imports/products/preview", files={"file": ("products.csv", data)}).json()
    assert result["can_confirm"]
    assert not any(p["code"] == "P1" for p in admin.get("/api/products").json())
    assert admin.post(f"/api/admin/imports/{result['id']}/confirm").status_code == 200
    assert admin.post(f"/api/admin/imports/{result['id']}/confirm").status_code == 409
    assert any(p["code"] == "P1" for p in admin.get("/api/products").json())


def test_import_error_does_not_partially_write(admin):
    data = "code,name,class_code,rate,min_rate,rate_type,effective_from\nP1,Test,property,0.5,0.3,fixed,2026-01-01\nP2,Bad,property,0.1,0.3,annual,2026-01-01\n"
    batch = admin.post("/api/admin/imports/products/preview", files={"file": ("p.csv", data)}).json()
    assert not batch["can_confirm"]
    assert admin.post(f"/api/admin/imports/{batch['id']}/confirm").status_code == 422
    assert not any(p["code"] == "P1" for p in admin.get("/api/products").json())


def test_upload_provenance_and_review_reset(admin):
    sid = survey(admin)
    response = admin.post(
        f"/api/surveys/{sid}/documents",
        files={
            "file": (
                "request.txt",
                "Запрос филиала\nСтраховая сумма: 100 000 000\nТариф: 0,5\nСтраховая премия: 503870".encode(),
            )
        },
    )
    assert response.status_code == 201, response.text
    fields = response.json()["extracted"]["fields"]
    assert fields["insured_sum"]["value"] == "100000000"
    assert fields["declared_rate"]["value"] == "0.5"
    assert fields["object_value"]["status"] == "unavailable"
    assert (
        admin.put(
            f"/api/surveys/{sid}", json=body(revision=2, declared_rate="0.5", declared_premium="503870")
        ).status_code
        == 200
    )
    report = admin.post(f"/api/surveys/{sid}/reports").json()["snapshot"]
    assert report["calculation"]["premium_discrepancy"] == "3870.00"
    assert report["documents"][0]["sha256"]


def test_manual_review_required(admin):
    sid = survey(admin)
    assert admin.put(f"/api/surveys/{sid}", json=body(manual_review_confirmed=False)).status_code == 200
    assert admin.post(f"/api/surveys/{sid}/reports").status_code == 422


def test_role_boundaries_and_approval(admin):
    sid = survey(admin)
    admin.put(f"/api/surveys/{sid}", json=body())
    rid = admin.post(f"/api/surveys/{sid}/reports").json()["id"]
    assert (
        admin.post(
            f"/api/reports/{rid}/decision", json={"decision": "approved", "comment": "Test approval"}
        ).status_code
        == 403
    )
    switch_user(admin, "underwriter", "underwriter")
    assert (
        admin.post(
            f"/api/reports/{rid}/decision",
            json={"decision": "approved", "comment": "Checked the supplied evidence"},
        ).status_code
        == 200
    )


def test_calibration_requires_three_years_and_actuary(admin):
    args = {
        "product_code": "DEMO-FIX",
        "target_loss_ratio": 0.6,
        "rationale": "Reviewed historical claims data",
    }
    assert admin.post("/api/admin/calibrations", json=args).status_code == 403
    switch_user(admin, "actuary", "actuary")
    assert admin.post("/api/admin/calibrations", json=args).status_code == 422
    for year in range(date.today().year - 3, date.today().year):
        r = admin.post(
            "/api/admin/losses",
            json={
                "product_code": "DEMO-FIX",
                "year": year,
                "claims": 10,
                "payments": "800",
                "premiums": "1000",
                "contracts": 100,
            },
        )
        assert r.status_code == 200, r.text
    response = admin.post("/api/admin/calibrations", json=args)
    assert response.status_code == 200, response.text
    assert response.json()["adjustment"] == "0.2"
    assert admin.post("/api/calculate", json=body()).json()["premium"] == "600000.00"
    admin.post(
        "/api/admin/losses",
        json={
            "product_code": "DEMO-FIX",
            "year": date.today().year - 1,
            "claims": 10,
            "payments": "600",
            "premiums": "1000",
            "contracts": 100,
        },
    )
    assert admin.post("/api/calculate", json=body()).json()["premium"] == "500000.00"


def test_employee_unique_and_first_login(admin):
    employee = {
        "login": "newuser",
        "password": "eight-chars",
        "phone": "+998901234567",
        "name": "Synthetic employee",
    }
    assert admin.post("/api/admin/employees", json=employee).status_code == 201
    assert admin.post("/api/admin/employees", json=employee).status_code == 409


def test_future_tariff_does_not_replace_current(admin):
    with admin.factory() as db:
        current = db.query(Product).filter_by(code="DEMO-FIX").first()
        db.add(
            Product(
                code="DEMO-FIX",
                effective_from=date(2099, 1, 1),
                data={**current.data, "rate": "1", "effective_from": "2099-01-01"},
            )
        )
        db.commit()
    assert admin.post("/api/calculate", json=body()).json()["premium"] == "500000.00"
    assert admin.post("/api/calculate", json=body(tariff_date="2099-01-01")).json()["premium"] == "1000000.00"


def test_invalid_file_rejected(admin):
    sid = survey(admin)
    assert (
        admin.post(f"/api/surveys/{sid}/documents", files={"file": ("evil.pdf", b"not pdf")}).status_code
        == 422
    )


def test_password_not_echoed_on_validation_error(client):
    secret = "a" * 200
    response = client.post("/api/auth/login", json={"login": "admin", "password": secret})
    assert response.status_code == 422
    assert secret not in response.text


def test_telegram_auth_signed_and_expiring():
    token = "test-token"
    fields = {"auth_date": "1000", "user": json.dumps({"id": 123456})}
    key = hmac.new(b"WebAppData", token.encode(), hashlib.sha256).digest()
    fields["hash"] = hmac.new(
        key, "\n".join(f"{k}={v}" for k, v in sorted(fields.items())).encode(), hashlib.sha256
    ).hexdigest()
    data = urlencode(fields)
    assert validate_telegram(data, token, timestamp=1100) == "123456"
    with pytest.raises(ValueError):
        validate_telegram(data, token, timestamp=1500)
    with pytest.raises(ValueError):
        validate_telegram(data, "wrong", timestamp=1100)


def test_blank_fields_distinct_from_missing():
    result = parse_document("Договор\nСтраховая сумма: ______\n".encode(), "contract.txt")
    assert result["fields"]["insured_sum"]["status"] == "blank"
    assert result["fields"]["object_value"]["status"] == "unavailable"
