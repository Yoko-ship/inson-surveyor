import io
import json
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
from openpyxl import load_workbook
from pydantic import ValidationError

from surveyor.calculations import calculate, valuation
from surveyor.db import Channel
from surveyor.napp_reference import REGIONAL_NOTE, parse_napp_reference
from surveyor.schemas import IndicatorInput
from surveyor.source_adapters import parse_public
from surveyor.sources import latest_indicators, store_indicator

FIXTURES = Path(__file__).parent / "fixtures"
URL = "https://napp.uz/storage/files/shares/opendata/2026/2Q/report.xlsx"


def workbook_change(sheet, cell, value):
    wb = load_workbook(FIXTURES / "napp-reference-2026-q2.xlsx")
    wb[sheet][cell] = value
    output = io.BytesIO()
    wb.save(output)
    wb.close()
    return output.getvalue()


def test_napp_reference_preserves_units_scopes_and_periods():
    rows, _ = parse_napp_reference((FIXTURES / "napp-reference-2026-q2.xlsx").read_bytes(), URL)
    current = [r for r in rows if r.observation_date == date(2026, 6, 30)]
    assert len(rows) == 653
    assert all(r.reference_only and r.rate_adjustment == 0 and r.annual_market_rate is None for r in rows)
    inson = {r.metric: r for r in current if r.subject == '"INSON" AJ' and r.region == "all"}
    assert abs(inson["napp_ref_company_premiums"].value - Decimal("100046222182.43714")) < Decimal("0.01")
    assert abs(inson["napp_ref_company_payments"].value - Decimal("28528510083.58001")) < Decimal("0.01")
    assert inson["napp_ref_claims_received"].value == 3516
    assert inson["napp_ref_claims_paid"].value == 3353
    assert inson["napp_ref_claims_refused"].value == 54
    assert inson["napp_ref_claims_unsettled"].value == 109
    assert any(r.class_code == "bundle_3_8_9" for r in rows)
    assert not any(r.class_code in {"vehicle", "fire", "property"} for r in rows)
    assert all(r.note == REGIONAL_NOTE for r in current if r.region != "all")
    assert not any(r.region == "1708" and r.metric == "napp_ref_inson_payment_premium_ratio" for r in rows)
    assert any(r.region == "1726" and r.metric == "napp_ref_inson_region_to_company_ratio" for r in rows)


@pytest.mark.parametrize(
    "sheet,cell,value",
    [
        ("2.12", "E4", "Unknown region"),
        ("2.12", "AE2", "thousand USD"),
        ("2.10", "J4", date(2025, 7, 1)),
        ("2.10", "J18", 1.5),
        ("3.5", "B7", "Unknown region"),
        ("2.13", "C21", 12),
        ("2.5", "C4", "Premiums, not payments"),
    ],
)
def test_napp_reference_rejects_changed_semantics(sheet, cell, value):
    with pytest.raises(ValueError):
        parse_napp_reference(workbook_change(sheet, cell, value), URL)


def test_napp_missing_is_not_zero():
    rows, _ = parse_napp_reference(workbook_change("2.10", "J18", None), URL)
    assert not any(
        r.subject == '"INSON" AJ'
        and r.metric == "napp_ref_claims_received"
        and r.observation_date == date(2026, 6, 30)
        for r in rows
    )


@pytest.mark.parametrize(
    "dataset,metric,unit,value,observed",
    [
        (888, "registered_thefts", "units", "49213", "2025-12-31"),
        (880, "registered_robberies", "units", "540", "2025-12-31"),
        (229, "mortality_per_mille", "Per mill", "4.7", "2025-12-31"),
        (246, "population_thousands", "thousand people", "38236.7", "2026-01-01"),
    ],
)
def test_siat_risk_units_and_observation_dates(dataset, metric, unit, value, observed):
    samples = json.loads((FIXTURES / "siat-risk-samples.json").read_text(encoding="utf-8"))
    rows, _ = parse_public(
        json.dumps(samples[str(dataset)]),
        {
            "format": "siat",
            "url": f"https://api.siat.stat.uz/media/uploads/sdmx/sdmx_data_{dataset}.json",
            "constants": {"metric": metric},
        },
    )
    last = rows[-1]
    assert last.region == "all"
    assert last.value == Decimal(value)
    assert last.observation_date.isoformat() == observed
    assert last.unit == unit


def test_company_series_are_not_collapsed_or_reversioned(admin):
    rows, _ = parse_napp_reference((FIXTURES / "napp-reference-2026-q2.xlsx").read_bytes(), URL)
    sample = next(r for r in rows if r.subject == '"INSON" AJ')
    with admin.factory() as db:
        first = store_indicator(db, "napp_reference", sample)
        assert store_indicator(db, "napp_reference", sample).id == first.id
        other = sample.model_copy(update={"subject": "Another company"})
        store_indicator(db, "napp_reference", other)
        db.commit()
        assert len(latest_indicators(db)) == 2
        assert db.get(Channel, "napp_reference").enabled
        assert not db.get(Channel, "stat_disasters").enabled
        assert not db.get(Channel, "listings").enabled


def test_reference_cannot_change_price_even_with_approved_rule():
    product = {"class_code": "fire", "rate_type": "annual", "rate": "1", "min_rate": "0.5"}
    inputs = {"insured_sum": "1000000", "term_days": 365, "object_type": "housing", "region": "1726"}
    metric = "napp_ref_inson_region_to_company_ratio"
    template = {
        "moderate_threshold": 20,
        "high_threshold": 50,
        "multipliers": {"low": "1"},
        "approved_by": "actuary",
        "indicator_rules": {
            metric: {
                "baseline": "1",
                "sensitivity": "1",
                "max_adjustment": "0.5",
                "object_types": ["housing"],
            }
        },
    }
    base = calculate(product, inputs, template)
    actual = calculate(
        product,
        inputs,
        template,
        [
            {
                "metric": metric,
                "value": "20",
                "region": "1726",
                "class_code": "fire",
                "approved_by": "actuary",
                "annual_market_rate": "99",
                "rate_adjustment": "0.5",
            }
        ],
    )
    assert actual == base
    with pytest.raises(ValidationError):
        IndicatorInput(
            metric=metric,
            value=1,
            period="2026",
            source_url=URL,
            observation_date=date(2026, 1, 1),
            unit="ratio",
            rate_adjustment="0.2",
        )


def test_auction_start_and_unproved_sale_are_excluded():
    base = {
        "label": "Equipment",
        "price": "100",
        "date": date.today().isoformat(),
        "source": "https://e-auksion.uz/lot/example",
        "same_item": True,
    }
    inputs = {
        "object_type": "vehicle",
        "object_value": "100",
        "comparables": [
            {**base, "evidence_kind": "auction_start"},
            {**base, "evidence_kind": "completed_sale"},
            {
                **base,
                "evidence_kind": "completed_sale",
                "transaction_reference": "Completed-sale protocol 123",
            },
            {**base, "source": "https://olx.uz/example", "evidence_kind": "asking_price"},
        ],
    }
    result = valuation(inputs)
    assert len(result["comparables"]) == 2
    assert len(result["rejected"]) == 2
    assert result["comparables"][0]["transaction_reference"] == "Completed-sale protocol 123"


def test_factor_catalog_is_authenticated_and_uncalibrated(admin):
    result = admin.get("/api/policy/factors").json()
    assert len(result["entries"]) == 139
    assert {c for row in result["entries"] for c in row["classes"]} == set(range(1, 19))
    assert len(result["pages"]) == 11
    assert all(row["coefficient"] is None for row in result["entries"])
    assert any(r["label"] == "Электромобиль" and r["classes"] == [3] for r in result["entries"])
    assert any(r["label"] == "Наводнение и сель" and r["classes"] == [8] for r in result["entries"])


def test_factor_catalog_requires_login(client):
    assert client.get("/api/policy/factors").status_code == 401


def test_reference_approval_and_report_snapshot(admin):
    from conftest import switch_user

    from surveyor.db import Report
    from surveyor.reports import sections
    from tests.test_workflows import body, survey

    sample = IndicatorInput(
        metric="napp_ref_inson_region_to_company_ratio",
        subject='"INSON" AJ',
        value="1.3",
        period="2026-01-01/2026-06-30",
        unit="ratio",
        region="1726",
        observation_date=date(2026, 6, 30),
        source_url=URL,
        note=REGIONAL_NOTE,
    )
    with admin.factory() as db:
        row = store_indicator(db, "napp_reference", sample)
        indicator_id = row.id
        db.commit()
    sid = survey(admin)
    assert admin.put(f"/api/surveys/{sid}", json=body()).status_code == 200
    response = admin.post(f"/api/surveys/{sid}/reports")
    assert response.status_code == 201
    snapshot = response.json()["snapshot"]
    assert snapshot["indicators"][0]["note"] == REGIONAL_NOTE
    with admin.factory() as db:
        report = db.get(Report, response.json()["id"])
        assert "Регион: Ташкент" in str(sections(report))
        assert REGIONAL_NOTE in str(sections(report))
        assert '"INSON" AJ' in str(sections(report))
    switch_user(admin, "actuary", "source-actuary")
    assert admin.post(f"/api/admin/indicators/{indicator_id}/approve").status_code == 422


def test_legacy_indicator_approval_survives_schema_defaults(admin):
    from surveyor.db import Indicator

    item = IndicatorInput(
        metric="registered_crimes",
        value=12,
        period="2025",
        unit="units",
        observation_date=date(2025, 12, 31),
        source_url=URL,
    )
    old = item.model_dump(mode="json", exclude={"subject", "reference_only", "note"})
    with admin.factory() as db:
        row = Indicator(channel_code="stat_crime", data={**old, "approved_by": "actuary"})
        db.add(row)
        db.flush()
        assert store_indicator(db, "stat_crime", item).id == row.id


def test_reference_collector_routes_and_stores_verified_workbook(admin, monkeypatch):
    from surveyor.napp import NAPP_INDEX
    from surveyor.sources import collect_channel

    content = (FIXTURES / "napp-reference-2026-q2.xlsx").read_bytes()

    def fetch(config, channel):
        assert channel == "napp"
        return f'<a href="{URL}">Workbook</a>'.encode() if config["url"] == NAPP_INDEX else content

    monkeypatch.setattr("surveyor.source_adapters.fetch_public", fetch)
    with admin.factory() as db:
        result = collect_channel(db, "napp_reference", force=True)
        assert result["status"] == "collected"
        assert result["count"] == 653
        assert len(latest_indicators(db)) > 300


def test_siat_changed_units_are_rejected():
    samples = json.loads((FIXTURES / "siat-risk-samples.json").read_text(encoding="utf-8"))["229"]
    for row in samples[0]["metadata"]:
        if row["name_en"] == "Unit of measurement":
            row["value_en"] = "percent"
    with pytest.raises(ValueError, match="единицы"):
        parse_public(
            json.dumps(samples),
            {"format": "siat", "url": URL, "constants": {"metric": "mortality_per_mille"}},
        )
