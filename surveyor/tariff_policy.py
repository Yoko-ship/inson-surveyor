"""Source-backed tariff catalogue. Reference minima never become chosen quote rates."""

import json
from decimal import Decimal
from functools import lru_cache
from pathlib import Path


@lru_cache(maxsize=1)
def catalog():
    return json.loads((Path(__file__).parent / "policies" / "inson-2025-09-23.json").read_text("utf-8"))


def entry_for(code):
    return next((r for r in catalog()["entries"] if r["code"] == code), None)


def minimum_for(entry, variant=None):
    if entry["kind"] == "variants":
        selected = next((v for v in entry["variants"] if v["key"] == variant), None)
        if not selected:
            raise ValueError("Выберите вариант продукта из тарифной политики")
        return selected["minimum_rate"]
    if variant:
        raise ValueError("У этого продукта нет такого варианта тарифа")
    return entry["minimum_rate"]


def check_tariff(code, rate=None, variant=None, commission=None, component_rates=None):
    entry = entry_for(code)
    if not entry:
        raise ValueError("Код отсутствует в предоставленной тарифной политике")
    checks = []
    component_rates = component_rates or {}
    if entry["kind"] == "components":
        if rate is not None or variant:
            raise ValueError("Для составного продукта укажите ставки каждого покрытия отдельно")
        expected = {c["key"] for c in entry["components"]}
        if set(component_rates) != expected:
            raise ValueError("Укажите ставки всех компонентов продукта без дополнительных ключей")
        for component in entry["components"]:
            checks.append(
                _rate_check(component["label"], component_rates[component["key"]], component["minimum_rate"])
            )
    else:
        if component_rates:
            raise ValueError("У этого продукта нет отдельных компонентных ставок в таблице")
        minimum = minimum_for(entry, variant)
        checks.append(_rate_check("Минимальный тариф", rate, minimum))
    if commission is not None:
        checks.append(
            _rate_check("Лимит агентского вознаграждения", commission, entry["commission_cap"], maximum=True)
        )
    known = all(c["passed"] is not None for c in checks)
    status = (
        "outside_policy"
        if any(c["passed"] is False for c in checks)
        else "within_document_limits"
        if known
        else "needs_details"
    )
    return {
        "status": status,
        "checks": checks,
        "policy_id": catalog()["id"],
        "source_page": entry["page"],
        "message": "Проверены только ограничения предоставленного документа. Итоговая премия и актуальность тарифа не подтверждены.",
    }


def _rate_check(label, value, bound, maximum=False):
    passed = None
    if value is not None and bound is not None:
        passed = Decimal(str(value)) <= Decimal(bound) if maximum else Decimal(str(value)) >= Decimal(bound)
    return {
        "label": label,
        "value": str(value) if value is not None else None,
        "bound": bound,
        "direction": "maximum" if maximum else "minimum",
        "passed": passed,
    }


def validate_product(data):
    """Validate both manual and imported versions; return immutable source evidence."""
    code = data.get("policy_code") or data["code"]
    entry = entry_for(code)
    if not entry:
        if data.get("policy_code"):
            raise ValueError("Код отсутствует в предоставленной тарифной политике")
        return None
    if entry_for(data["code"]) and data["code"] != code:
        raise ValueError("Код продукта не соответствует выбранной строке тарифной политики")
    if entry["kind"] in {"components", "unspecified", "clarification"}:
        raise ValueError(
            "Для этой строки нужны уточнённые условия или отдельный расчёт компонентов; единый тариф недоступен"
        )
    minimum = minimum_for(entry, data.get("policy_variant"))
    if minimum is not None:
        floor = Decimal(minimum)
        if (
            Decimal(str(data["min_rate"])) < floor
            or Decimal(str(data["rate"])) < floor
            or any(Decimal(str(v)) < floor for v in data.get("program_rates", {}).values())
        ):
            raise ValueError(f"Минимум по тарифной политике: {minimum}%")
    if not data.get("policy_current_confirmed"):
        raise ValueError("Подтвердите актуальность тарифной политики для этой версии продукта")
    if len(data.get("policy_basis_reference", "")) < 10:
        raise ValueError("Укажите документ и пункт, подтверждающие базу ставки и дату начала действия")
    if len(data.get("policy_terms_reference", "")) < 10:
        raise ValueError("Укажите правила или программу страхования для этой версии продукта")
    if entry["kind"] == "head_office" and len(data.get("policy_approval_reference", "")) < 10:
        raise ValueError("Тарифная политика требует согласование с ЦО: укажите документ согласования")
    if entry["kind"] == "program" and (data["rate_type"] != "program" or not data.get("program_rates")):
        raise ValueError("Для продукта нужны утверждённые ставки программы")
    if (entry["kind"] == "normative" or entry.get("requires_normative_terms")) and data[
        "rate_type"
    ] != "normative":
        raise ValueError("Для обязательного страхования нужен нормативный тариф с источником")
    basis = (
        data.get("program_basis")
        if data["rate_type"] == "program"
        else data.get("normative_basis")
        if data["rate_type"] == "normative"
        else data["rate_type"]
    )
    if entry["period_basis"] in {"fixed", "voyage"} and basis != "fixed":
        raise ValueError(
            "В документе указана ставка за период или перевозку; годовое пропорционирование недопустимо"
        )
    commission = data.get("agent_commission_percent")
    if commission is not None:
        if entry["commission_cap"] is None:
            raise ValueError("Лимит комиссии в документе не определён; требуется уточнение")
        if Decimal(str(commission)) > Decimal(entry["commission_cap"]):
            raise ValueError(f"Лимит агентского вознаграждения: {entry['commission_cap']}%")
    return {
        "policy_id": catalog()["id"],
        "document_date": catalog()["document_date"],
        "sha256": catalog()["sha256"],
        "source_filename": catalog()["source_filename"],
        "page": entry["page"],
        "code": code,
        "variant": data.get("policy_variant"),
        "minimum_rate": minimum,
        "commission_cap": entry["commission_cap"],
        "period_basis": entry["period_basis"],
        "amount_basis": entry["amount_basis"],
    }
