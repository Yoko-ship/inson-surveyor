from datetime import date
from decimal import Decimal

import pytest

from surveyor.calculations import calculate, loss_summary, valuation
from surveyor.schemas import ProductInput


def product(**kwargs):
    return {
        "code": "P",
        "name": "Product",
        "class_code": "vehicle",
        "rate": "0.5",
        "min_rate": "0.3",
        "rate_type": "annual",
        "effective_from": "2020-01-01",
        **kwargs,
    }


def inputs(**kwargs):
    return {"insured_sum": "100000000", "object_value": "100000000", "term_days": 1095, **kwargs}


@pytest.mark.parametrize("days", [1, 30, 180, 365, 730, 1095, 3650])
@pytest.mark.parametrize("kind", ["annual", "fixed"])
def test_term_formula(days, kind):
    result = calculate(product(rate_type=kind), inputs(term_days=days))
    expected = Decimal("500000") * (Decimal(days) / 365 if kind == "annual" else 1)
    assert abs(Decimal(result["premium"]) - expected) <= Decimal("0.005")
    assert abs(
        Decimal(result["annualized_rate"]) - Decimal("0.5") * (Decimal(365) / days if kind == "fixed" else 1)
    ) <= Decimal("0.000000005")


def test_spec_examples():
    assert calculate(product(), inputs())["premium"] == "1500000.00"
    assert calculate(product(rate_type="fixed"), inputs())["premium"] == "500000.00"


@pytest.mark.parametrize("minimum", ["0.1", "0.3", "0.5", "2"])
def test_minimum_never_breached(minimum):
    template = {
        "feature_weights": {},
        "moderate_threshold": 20,
        "high_threshold": 50,
        "multipliers": {"low": "0.5"},
        "max_adjustment": "0.5",
        "indicator_metrics": ["regional_risk"],
    }
    calc = calculate(
        product(min_rate=minimum),
        inputs(),
        template,
        [{"metric": "regional_risk", "rate_adjustment": "-0.5"}],
        {"adjustment": "-0.5"},
    )
    assert Decimal(calc["recommended_rate"]) >= Decimal(minimum)


def test_program_missing_is_undefined():
    assert calculate(product(rate_type="program", program_rates={}), inputs())["status"] == "undefined"


def test_program_fixed_and_comparison():
    result = calculate(
        product(rate_type="program", program_rates={"A": "0.6"}, program_basis="fixed"),
        inputs(program="A", declared_rate="0.6", declared_premium="600000"),
    )
    assert result["premium"] == "600000.00"
    assert result["premium_discrepancy"] == "0.00"


def test_market_uses_annual_equivalent():
    result = calculate(
        product(rate_type="fixed"),
        inputs(declared_rate="0.5"),
        indicators=[{"metric": "market", "class_code": "vehicle", "annual_market_rate": "0.2"}],
    )
    assert result["comparison"] == "within_range"


def test_stale_market_not_used():
    result = calculate(
        product(),
        inputs(),
        indicators=[
            {"metric": "market", "class_code": "vehicle", "annual_market_rate": "0.9", "stale": True}
        ],
    )
    assert result["annual_market_rate"] is None


def test_normative_cannot_get_discretionary_adjustment():
    result = calculate(
        product(rate_type="normative", normative_basis="fixed", normative_source="https://lex.uz/test"),
        inputs(),
        calibration={"adjustment": "0.2"},
    )
    assert result["premium"] == "500000.00"
    assert result["loss_adjustment"] == "0"


@pytest.mark.parametrize(
    "bad",
    [
        {"rate": "0.1"},
        {"rate_type": "invalid"},
        {"rate_type": "normative"},
        {"min_rate": "-1"},
        {"rate": "NaN"},
    ],
)
def test_invalid_product(bad):
    with pytest.raises(ValueError):
        ProductInput.model_validate(product(**bad))


def comparable(price, **kwargs):
    return {
        "price": str(price),
        "date": "2026-09-01",
        "source": "manual listing",
        "same_item": True,
        "label": "same car",
        **kwargs,
    }


def test_valuation_excludes_outlier_and_keeps_original_median():
    result = valuation(
        inputs(
            object_type="vehicle",
            object_value="120",
            comparables=[
                comparable(100),
                comparable(120, original_price="110", edit_reason="Correction"),
                comparable(10000),
            ],
        ),
        today=date(2026, 10, 1),
    )
    assert result["estimate"] == "110.00"
    assert result["raw_median"] == "110.00"
    assert len(result["rejected"]) == 1
    assert result["status"] == "confirmed"


@pytest.mark.parametrize(
    "change",
    [
        {"date": "2025-01-01"},
        {"date": "2027-01-01"},
        {"same_item": False},
        {"price": "0"},
        {"currency": "USD"},
        {"original_price": "1"},
    ],
)
def test_ineligible_comparables(change):
    result = valuation(
        inputs(comparables=[comparable(100, **change)] if "price" not in change else [comparable(0)]),
        today=date(2026, 10, 1),
    )
    assert result["estimate"] is None
    assert result["rejected"]


def test_equipment_depreciation():
    result = valuation(
        inputs(object_type="equipment", purchase_price="200", depreciation_percent="25", object_value="150")
    )
    assert result["estimate"] == "150.00"
    assert result["status"] == "confirmed"


def test_large_requires_two_sourced_methods():
    result = valuation(inputs(object_type="large", appraiser_value="200"))
    assert result["estimate"] is None


def test_loss_ratios_with_zero_denominators():
    result = loss_summary([{"year": 2025, "claims": 2, "payments": "100", "premiums": "0", "contracts": 0}])[
        0
    ]
    assert result["loss_ratio"] is None
    assert result["frequency"] is None
