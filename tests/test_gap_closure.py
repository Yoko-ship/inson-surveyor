from datetime import date, timedelta
from unittest.mock import Mock

import pytest
from pydantic import ValidationError
from sqlalchemy import select

from surveyor.calculations import valuation
from surveyor.db import Audit, Channel, now
from surveyor.documents import parse_document
from surveyor.schemas import SurveyInput
from surveyor.sources import collect_all, collect_cbu
from tests.test_adapters import fake_cbu
from tests.test_workflows import body, survey


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("100 000 000", "100000000"),
        ("100,000,000", "100000000"),
        ("100.000.000", "100000000"),
        ("100,000,000.50 UZS", "100000000.50"),
        ("100.000.000,50 UZS", "100000000.50"),
        ("100\u202f000\u202f000,50", "100000000.50"),
        ("100,000", None),
        ("100 00", None),
        ("100,00,00", None),
        ("100 million UZS", None),
        ("1e8", None),
        ("100-200", None),
        ("100 - 200", None),
        ("100 миллионов сум", None),
        ("100 млрд", None),
        ("1_000", None),
        ("100 USD", None),
    ],
)
def test_amount_formats_never_truncate_grouped_values(raw, expected):
    result = parse_document(f"Insured sum: {raw}".encode(), "contract.txt")
    field = result["fields"]["insured_sum"]
    assert field["value"] == expected
    assert field["status"] == ("extracted" if expected is not None else "needs_review")


def test_dates_derive_duration_but_preserve_explicit_contract_term():
    text = "Contract\nStart date: 01.01.2024\nEnd date: 01.01.2027"
    field = parse_document(text.encode(), "contract.txt")["fields"]["term_days"]
    assert field["value"] == "1096"
    assert field["derived_from"] == "contract_dates"
    field = parse_document((text + "\nTerm days: 1095").encode(), "contract.txt")["fields"]["term_days"]
    assert field["value"] == "1095"
    assert "derived_from" not in field


def test_input_date_difference_requires_an_explanation_for_override():
    inputs = body(contract_start="2024-01-01", contract_end="2027-01-01")
    with pytest.raises(ValidationError, match="Срок отличается"):
        SurveyInput(**inputs)
    assert (
        SurveyInput(**{**inputs, "override_reason": "Contract explicitly uses a 365-day basis"}).term_days
        == 1095
    )
    inputs.pop("term_days")
    assert SurveyInput(**inputs).term_days == 1096
    with pytest.raises(ValidationError, match="Дата окончания"):
        SurveyInput(**{**inputs, "contract_end": "2023-12-31"})


def test_document_date_edit_recalculates_derived_duration(admin):
    sid = survey(admin)
    doc = admin.post(
        f"/api/surveys/{sid}/documents",
        files={"file": ("contract.txt", "Contract\nStart date: 01.01.2024\nEnd date: 01.01.2027")},
    ).json()
    response = admin.put(
        f"/api/documents/{doc['id']}/review",
        json={
            "revision": doc["revision"],
            "kind": "contract",
            "fields": {"contract_end": "2025-01-01"},
            "reason": "Corrected the end date from the signed document",
        },
    )
    assert response.status_code == 200, response.text
    field = response.json()["extracted"]["fields"]["term_days"]
    assert field["value"] == "366" and field["original"] == "1096"


@pytest.mark.parametrize("stated_term", [None, 365])
def test_document_dates_catch_wrong_entered_duration(admin, stated_term):
    sid = survey(admin)
    text = "Contract\nStart date: 01.01.2024\nEnd date: 01.01.2027"
    if stated_term:
        text += f"\nTerm days: {stated_term}"
    doc = admin.post(
        f"/api/surveys/{sid}/documents",
        files={"file": ("contract.txt", text)},
    ).json()
    assert (
        admin.put(f"/api/surveys/{sid}", json=body(revision=doc["revision"], term_days=365)).status_code
        == 200
    )
    report = admin.post(f"/api/surveys/{sid}/reports").json()["snapshot"]
    assert any(c["field"] == "term_days" for c in report["conflicts"])


def test_valuation_range_rendered_and_purchase_requires_evidence(admin):
    sid = survey(admin)
    comparables = [
        {
            "label": str(p),
            "price": str(p),
            "source": "https://example.test/listing",
            "date": str(date.today()),
        }
        for p in (90000000, 110000000)
    ]
    assert (
        admin.put(
            f"/api/surveys/{sid}", json=body(object_type="vehicle", comparables=comparables, language="en")
        ).status_code
        == 200
    )
    rid = admin.post(f"/api/surveys/{sid}/reports").json()["id"]
    lines = admin.get(f"/api/reports/{rid}").json()["sections"][1]["lines"]
    assert "Value range minimum, UZS: 90000000.00" in lines
    assert "Value range maximum, UZS: 110000000.00" in lines
    invalid = body(object_type="equipment", purchase_price="100000000", depreciation_percent="20")
    assert admin.put(f"/api/surveys/{sid}", json={**invalid, "revision": 2}).status_code == 422
    assert valuation({**invalid, "object_value": "80000000"})["status"] == "clarify"
    assert (
        admin.put(
            f"/api/surveys/{sid}",
            json={
                **invalid,
                "revision": 2,
                "purchase_source": "Invoice 123",
                "purchase_date": str(date.today()),
            },
        ).status_code
        == 200
    )


def test_cbu_storage_failure_is_visible_and_retries_next_hour(admin, monkeypatch):
    fake_cbu(
        monkeypatch,
        200,
        [{"Ccy": "USD", "Rate": "12000", "Nominal": "1", "Date": date.today().strftime("%d.%m.%Y")}],
    )
    with admin.factory() as db:
        with monkeypatch.context() as local:
            local.setattr(
                "surveyor.sources.host_lock", Mock(side_effect=OSError("private path must not appear"))
            )
            assert collect_cbu(db)["status"] == "error"
        channel = db.get(Channel, "cbu")
        assert channel.enabled and channel.error and "private path" not in channel.error
        assert collect_cbu(db)["status"] == "cached"
        channel.last_attempt = now() - timedelta(hours=1, seconds=1)
        db.commit()
        assert collect_cbu(db)["status"] == "collected"
        assert channel.last_success and channel.error is None


def test_broken_channel_does_not_stop_other_channels(admin, monkeypatch):
    visited = []

    def collect(db, code):
        visited.append(code)
        if code == "cbu":
            raise RuntimeError("private detail")
        return {"status": "collected", "channel": code}

    monkeypatch.setattr("surveyor.sources.collect_channel", collect)
    with admin.factory() as db:
        result = collect_all(db)
        assert len(visited) > 1
        assert any(r["status"] == "error" for r in result)
        assert any(r["status"] == "collected" for r in result)
        assert "private detail" not in db.get(Channel, "cbu").error


def test_worker_maintains_after_collection_failure(admin, monkeypatch):
    from surveyor import worker

    monkeypatch.setattr(worker, "collect_all", Mock(side_effect=RuntimeError("private detail")))
    maintenance = Mock()
    monkeypatch.setattr(worker, "maintain", maintenance)
    worker.run_cycle(admin.factory)
    maintenance.assert_called_once()
    with admin.factory() as db:
        assert db.scalar(select(Audit).where(Audit.action == "worker.failed"))


def test_borrower_requires_owned_evidence_and_freezes_score(admin):
    sid = survey(admin)
    doc = admin.post(
        f"/api/surveys/{sid}/documents", files={"file": ("bureau.txt", "Bureau report: 750 / 1000")}
    ).json()
    borrower = {
        "organization_name": "LLC Example",
        "bureau_name": "Example bureau",
        "document_id": doc["id"],
        "report_date": str(date.today()),
        "score": "750",
        "score_scale": "0-1000",
        "summary": "Verified against uploaded report",
    }
    response = admin.put(
        f"/api/surveys/{sid}", json=body(revision=doc["revision"], borrower=borrower, language="en")
    )
    assert response.status_code == 200, response.text
    report = admin.post(f"/api/surveys/{sid}/reports").json()
    assert report["snapshot"]["calculation"]["premium"] == "500000.00"
    lines = admin.get(f"/api/reports/{report['id']}").json()["sections"][0]["lines"]
    assert "Bureau score: 750" in lines
    assert any("bureau.txt" in line and "SHA256" in line for line in lines)
    other = survey(admin)
    assert admin.put(f"/api/surveys/{other}", json=body(borrower=borrower)).status_code == 422
    assert (
        admin.put(
            f"/api/surveys/{sid}",
            json=body(revision=doc["revision"] + 1, borrower={**borrower, "score": "800"}),
        ).status_code
        == 200
    )
    assert (
        admin.get(f"/api/reports/{report['id']}").json()["snapshot"]["inputs"]["borrower"]["score"] == "750"
    )


def test_market_quote_annualization_and_source_mapping(admin):
    response = admin.post(
        "/api/admin/market-quotes",
        json={
            "class_code": "property",
            "object_type": "housing",
            "region": "all",
            "rate": "0.6",
            "basis": "fixed",
            "term_days": 1095,
            "coverage": "Comparable property coverage and deductible",
            "source_url": "https://example.test/quote",
            "observation_date": str(date.today()),
        },
    )
    assert response.status_code == 201, response.text
    assert response.json()["annual_market_rate"] == "0.2"
    calc = admin.post("/api/calculate", json=body(object_type="housing", declared_rate="0.5")).json()
    assert calc["annual_market_rate"] == "0.2" and calc["comparison"] == "within_range"
    assert (
        admin.post("/api/calculate", json=body(object_type="equipment")).json()["annual_market_rate"] is None
    )

    response = admin.post(
        "/api/admin/sources/stat/indicators",
        json={
            "metric": "registered_crimes",
            "region": "all",
            "period": str(date.today().year),
            "value": "1200",
            "unit": "count",
            "source_url": "https://stat.uz/",
            "observation_date": str(date.today()),
        },
    )
    assert response.status_code == 200, response.text
    before = next(
        t
        for t in admin.get("/api/admin/source-coverage").json()["templates"]
        if t["class_code"] == "property"
    )
    assert "registered_crimes" in before["unmapped_metrics"]
    assert "regional_risk" in before["missing_metrics"]
    assert before["market_available"]
    response = admin.post(
        "/api/admin/templates",
        json={
            "class_code": "property",
            "name": "Property policy",
            "multipliers": {"low": "1", "moderate": "1.1", "high": "1.2"},
            "indicator_rules": {
                "registered_crimes": {
                    "baseline": "1000",
                    "sensitivity": "0.1",
                    "max_adjustment": "0.1",
                    "object_types": ["housing"],
                }
            },
        },
    )
    assert response.status_code == 201, response.text
    calc = admin.post("/api/calculate", json=body(object_type="housing")).json()
    assert calc["regional_adjustment"] == "0.02"
    assert calc["applied_metrics"] == ["registered_crimes"]
    after = next(
        t
        for t in admin.get("/api/admin/source-coverage").json()["templates"]
        if t["class_code"] == "property"
    )
    assert after["linked_metrics"] == ["registered_crimes"] and not after["approved"]
