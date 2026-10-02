import csv
import io
from datetime import date
from decimal import Decimal

import pytest

from surveyor.calculations import calculate
from surveyor.db import Report
from surveyor.reports import sections
from surveyor.reserves import classify_rnp
from surveyor.schemas import ProductInput, RnpInput
from surveyor.tariff_policy import catalog, check_tariff, entry_for


def configured(**changes):
    return {
        "code": "0301",
        "name": "Транспорт в залоге",
        "class_code": "vehicle",
        "rate": "0.8",
        "min_rate": "0.6",
        "rate_type": "fixed",
        "effective_from": "2026-01-01",
        "policy_code": "0301",
        "policy_current_confirmed": True,
        "policy_basis_reference": "Тестовое основание срока и даты действия",
        "policy_terms_reference": "Тестовые правила продукта, пункт 10",
        **changes,
    }


def test_catalog_preserves_source_cells_and_gaps():
    data = catalog()
    assert len(data["entries"]) == len({r["code"] for r in data["entries"]}) == 179
    assert data["effective_from"] is None and data["current_confirmed"] is False
    assert {r["code"] for r in data["entries"] if r["kind"] == "unspecified"} == {"1318", "1420", "1422"}
    # Regression fixtures transcribed from the original scan, not its damaged OCR layer.
    assert entry_for("0317")["minimum_rate"] == "1.8"
    assert entry_for("0801")["minimum_rate"] == "0.03"
    assert entry_for("0309")["variants"][1]["minimum_rate"] == "1.5"
    assert entry_for("0327")["commission_cap"] == "0"
    assert entry_for("1002")["commission_cap"] == "20"
    assert entry_for("1304")["minimum_rate"] is None
    assert entry_for("1411")["commission_cap"] is None
    assert entry_for("0319")["amount_basis"] == "limit"


def test_variant_boundary_and_commission_are_independent():
    assert check_tariff("0309", "1.2", "individual")["status"] == "within_document_limits"
    assert check_tariff("0309", "1.2", "legal_entity")["status"] == "outside_policy"
    assert check_tariff("0327", "0.8", "electric", "0.01")["status"] == "outside_policy"
    assert check_tariff("0201", "1")["status"] == "needs_details"
    with pytest.raises(ValueError):
        check_tariff("0309", "1.5")


def test_composite_rates_cannot_be_flattened_or_partially_checked():
    with pytest.raises(ValueError):
        check_tariff("0305", rate="2.6")
    with pytest.raises(ValueError):
        check_tariff("0305", component_rates={"vehicle": "1.1"})
    result = check_tariff("0305", component_rates={"vehicle": "1.1", "accident": "0.5", "liability": "0.99"})
    assert result["status"] == "outside_policy"
    assert [c["passed"] for c in result["checks"]] == [True, True, False]


@pytest.mark.parametrize(
    "changes",
    [
        {"rate": "0.59", "min_rate": "0.59"},
        {"min_rate": "0.3"},
        {"program_rates": {"discount": "0.59"}},
        {"policy_current_confirmed": False},
        {"policy_basis_reference": ""},
        {"policy_terms_reference": ""},
        {"agent_commission_percent": "25.01"},
        {"policy_variant": "made-up"},
        {"policy_code": "0308"},
    ],
)
def test_source_requirements_cannot_be_bypassed_on_save(changes):
    with pytest.raises(ValueError):
        ProductInput(**configured(**changes))


@pytest.mark.parametrize("code", ["0116", "0701", "1426", "1428"])
def test_explicit_period_rate_cannot_be_annualized_for_pricing(code):
    with pytest.raises(ValueError, match="годовое"):
        ProductInput(**configured(code=code, policy_code=code, rate="1", min_rate="1", rate_type="annual"))


def test_program_head_office_and_composite_requirements():
    with pytest.raises(ValueError, match="программы"):
        ProductInput(**configured(code="0104", policy_code="0104"))
    with pytest.raises(ValueError, match="согласование"):
        ProductInput(**configured(code="0201", policy_code="0201"))
    with pytest.raises(ValueError, match="компонентов"):
        ProductInput(**configured(code="0305", policy_code="0305"))
    p = ProductInput(
        **configured(
            code="0201", policy_code="0201", policy_approval_reference="Тестовое согласование ЦО № 1"
        )
    )
    assert p.rate == Decimal("0.8")


def test_catalog_is_authenticated_and_does_not_seed_live_rates(admin):
    assert len(admin.get("/api/policy/catalog").json()["entries"]) == 179
    assert all(p["code"].startswith("DEMO-") for p in admin.get("/api/products").json())
    assert admin.get("/api/policy/source").status_code == 404
    admin.post("/api/auth/logout")
    assert admin.get("/api/policy/catalog").status_code == 401
    assert admin.get("/api/policy/source").status_code == 401


def test_import_preview_rejects_policy_floor_bypass(admin):
    row = configured(rate="0.59", min_rate="0.59")
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=list(row))
    writer.writeheader()
    writer.writerow(row)
    result = admin.post(
        "/api/admin/imports/products/preview", files={"file": ("policy.csv", output.getvalue().encode())}
    )
    assert result.status_code == 200
    assert result.json()["can_confirm"] is False
    assert not any(p["code"] == "0301" for p in admin.get("/api/products").json())


def test_saved_source_snapshot_and_commission_do_not_change_premium(admin):
    response = admin.post("/api/admin/products", json=configured(agent_commission_percent="25"))
    assert response.status_code == 201, response.text
    product = response.json()
    assert product["tariff_policy"]["sha256"] == catalog()["sha256"]
    assert product["tariff_policy"]["page"] == 4
    calc = calculate(product, {"insured_sum": "100000000", "term_days": 1095})
    assert calc["premium"] == "800000.00"
    assert calc["minimum_premium"] == "600000.00"


def test_company_policy_does_not_apply_demo_risk_adjustments():
    from surveyor.tariff_policy import validate_product

    product = configured()
    product["tariff_policy"] = validate_product(product)
    template = {
        "feature_weights": {"visible_damage": 100},
        "high_threshold": 50,
        "moderate_threshold": 20,
        "multipliers": {"low": "1", "moderate": "1.5", "high": "2"},
    }
    inputs = {"insured_sum": "100000000", "features": ["visible_damage"]}
    result = calculate(product, inputs, template)
    assert result["premium"] == "800000.00"
    assert result["risk_score"] is None
    template["approved_by"] = "actuary-test"
    assert calculate(product, inputs, template)["premium"] == "1600000.00"


@pytest.mark.parametrize(
    "context, group",
    [
        ({"insurance_class": 1}, 1),
        ({"insurance_class": 3}, 1),
        ({"insurance_class": 12}, 1),
        ({"insurance_class": 17}, 1),
        ({"insurance_class": 14}, 2),
        ({"insurance_class": 15}, 2),
        ({"insurance_class": 13}, None),
        ({"insurance_class": 13, "borrower_nonrepayment": False}, 1),
        ({"insurance_class": 13, "borrower_nonrepayment": True}, 2),
        ({"insurance_class": 16}, None),
        ({"insurance_class": 16, "crop_insurance": True}, 4),
        ({"insurance_class": 16, "crop_insurance": False}, 2),
        ({"insurance_class": 7, "open_dates": True}, 3),
        ({"reinsurance": "non_proportional"}, 1),
        ({"insurance_class": 16, "crop_insurance": True, "reinsurance": "proportional"}, 4),
        ({"reinsurance": "non_proportional", "open_dates": True}, None),
    ],
)
def test_rnp_contract_exceptions(context, group):
    assert classify_rnp(RnpInput(**context).model_dump())["group"] == group


def test_rnp_rejects_conflicting_class_flags(admin):
    result = admin.post("/api/policy/rnp/classify", json={"insurance_class": 3, "crop_insurance": True})
    assert result.status_code == 422


def test_report_keeps_rnp_and_policy_evidence_without_changing_risk(admin):
    admin.post("/api/admin/products", json=configured())
    survey = admin.post("/api/surveys", json={"title": "Проверка политики"}).json()
    body = {
        "revision": 1,
        "product_code": "0301",
        "insured_sum": "100000000",
        "object_value": "100000000",
        "region": "1726",
        "tariff_date": date.today().isoformat(),
        "manual_review_confirmed": True,
        "rnp_context": {"insurance_class": 13, "borrower_nonrepayment": True},
    }
    response = admin.put(f"/api/surveys/{survey['id']}", json=body)
    assert response.status_code == 200, response.text
    response = admin.post(f"/api/surveys/{survey['id']}/reports")
    assert response.status_code == 201, response.text
    with admin.factory() as db:
        report = db.query(Report).filter_by(survey_id=survey["id"]).one()
        assert report.snapshot["rnp_classification"]["group"] == 2
        assert report.snapshot["calculation"]["risk_score"] is None
        rendered = str(sections(report))
        assert "Учётная группа РНП: 2" in rendered
        assert catalog()["sha256"] in rendered
