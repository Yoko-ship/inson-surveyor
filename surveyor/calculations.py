"""Pure deterministic functions. Rates are percentages; all money uses Decimal."""

from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from statistics import median

D = Decimal


def money(value):
    return str(D(value).quantize(D("0.01"), rounding=ROUND_HALF_UP))


def number(value):
    return str(D(value).quantize(D("0.00000001"), rounding=ROUND_HALF_UP).normalize())


def calculate(product, inputs, template=None, indicators=(), calibration=None):
    days = int(inputs.get("term_days", 365))
    amount = D(str(inputs["insured_sum"]))
    if days <= 0 or amount <= 0:
        raise ValueError("Сумма и срок должны быть положительными")
    kind = product["rate_type"]
    basis = kind
    rate = D(product["rate"])
    minimum = D(product["min_rate"])
    warnings = []
    if product.get("tariff_policy") and template and not template.get("approved_by"):
        template = None
        warnings.append("Поправки риска не применены: шаблон не утверждён страховщиком")
    if product.get("tariff_policy", {}).get("amount_basis") == "limit":
        warnings.append("База тарифа — сумма лимита; в поле страховой суммы должен быть указан лимит")
    if kind == "program":
        selected = product.get("program_rates", {}).get(inputs.get("program"))
        if selected is None:
            return {
                "status": "undefined",
                "reason": "Ставка не определена: выберите утверждённую программу",
                "warnings": [],
            }
        rate, basis = D(selected), product["program_basis"]
    if kind == "normative":
        basis = product.get("normative_basis")
        if basis not in {"annual", "fixed"} or not product.get("normative_source"):
            return {
                "status": "undefined",
                "reason": "Ставка не определена: нет нормативной формулы",
                "warnings": [],
            }
    score = None
    level = "unavailable"
    multiplier = D(1)
    if template:
        score = min(
            100, sum(template.get("feature_weights", {}).get(f, 0) for f in set(inputs.get("features", [])))
        )
        level = (
            "high"
            if score >= template["high_threshold"]
            else "moderate"
            if score >= template["moderate_threshold"]
            else "low"
        )
        multiplier = D(str(template["multipliers"][level]))
        if not template.get("approved_by"):
            warnings.append("Поправки и страховой балл — оценка разработчика, не утверждено страховщиком")
    else:
        warnings.append("Шаблон класса отсутствует; аналитика риска недоступна")
    max_adj = D(str((template or {}).get("max_adjustment", "0.2")))
    regional = D(0)
    market = None
    used = []
    applied_metrics = set()
    from surveyor.regions import region_code

    # Prefer an object's regional series over a national series of the same metric.
    indicators = sorted(
        indicators,
        key=lambda i: (
            region_code(i.get("region", "all")) == region_code(inputs.get("region", "all"))
            and i.get("region", "all") != "all",
            i.get("object_type", "all") == inputs.get("object_type"),
            i.get("observation_date", ""),
        ),
        reverse=True,
    )
    for indicator in indicators:
        if indicator.get("stale"):
            continue
        metric = indicator["metric"]
        relevant = indicator.get("object_type", "all") in {"all", inputs.get("object_type")}
        rule = (template or {}).get("indicator_rules", {}).get(metric)
        if (
            relevant
            and rule
            and inputs.get("object_type") in rule["object_types"]
            and metric not in applied_metrics
        ):
            delta = (D(str(indicator["value"])) / D(str(rule["baseline"])) - 1) * D(str(rule["sensitivity"]))
            bound = D(str(rule["max_adjustment"]))
            regional += max(-bound, min(bound, delta))
            used.append(
                {**indicator, "rule": rule, "computed_adjustment": number(max(-bound, min(bound, delta)))}
            )
            applied_metrics.add(metric)
        elif (
            relevant
            and metric in (template or {}).get("indicator_metrics", [])
            and metric not in applied_metrics
            and (not product.get("tariff_policy") or indicator.get("approved_by"))
        ):
            applied_metrics.add(metric)
            regional += D(str(indicator.get("rate_adjustment", 0)))
            used.append(indicator)
            if D(str(indicator.get("rate_adjustment", 0))) and not indicator.get("approved_by"):
                warnings.append("Поправки открытых данных — экспертные, не утверждены страховщиком")
        if (
            relevant
            and indicator.get("annual_market_rate") is not None
            and indicator.get("class_code") == product["class_code"]
        ):
            if market is not None:
                continue
            market = D(str(indicator["annual_market_rate"]))
            used.append(indicator)
    regional = min(max_adj, max(-max_adj, regional))
    loss_adj = D(0)
    if calibration:
        loss_adj = min(max_adj, max(-max_adj, D(str(calibration["adjustment"]))))
    # Statutory tariffs may not be changed by discretionary risk/market factors.
    if kind == "normative":
        multiplier, regional, loss_adj = D(1), D(0), D(0)
    elif not applied_metrics:
        warnings.append(
            "Региональная поправка не рассчитана: нет актуальных данных, связанных с правилами для этого объекта"
        )
    if market is None:
        warnings.append(
            "Рыночная годовая ставка недоступна: требуется сопоставимая котировка с источником и датой"
        )
    recommended = max(minimum, rate * multiplier * (1 + regional) * (1 + loss_adj))
    time_factor = D(days) / 365 if basis == "annual" else D(1)
    annual_factor = D(365) / days if basis == "fixed" else D(1)
    annual_rate = recommended * annual_factor
    declared = inputs.get("declared_rate")
    declared_premium = inputs.get("declared_premium")
    comparison = "unavailable"
    if declared is not None:
        declared = D(str(declared))
        comparison = (
            "below_minimum"
            if declared < minimum
            else "above_market"
            if market is not None and declared * annual_factor > market
            else "within_range"
            if market is not None
            else "above_minimum_market_unavailable"
        )
    premium = amount * recommended / 100 * time_factor
    expected_document = amount * declared / 100 * time_factor if declared is not None else premium
    discrepancy = D(str(declared_premium)) - expected_document if declared_premium is not None else None
    if market is not None and market < minimum * annual_factor:
        warnings.append("Рыночная ставка ниже минимума компании; минимум сохраняется")
    return {
        "status": "calculated",
        "rate_type": kind,
        "basis": basis,
        "term_days": days,
        "base_rate": number(rate),
        "minimum_rate": number(minimum),
        "recommended_rate": number(recommended),
        "annualized_rate": number(annual_rate),
        "annualized_minimum": number(minimum * annual_factor),
        "annual_market_rate": number(market) if market is not None else None,
        "premium": money(premium),
        "minimum_premium": money(amount * minimum / 100 * time_factor),
        "risk_score": score,
        "risk_level": level,
        "risk_multiplier": number(multiplier),
        "regional_adjustment": number(regional),
        "loss_adjustment": number(loss_adj),
        "comparison": comparison,
        "document_expected_premium": money(expected_document),
        "premium_discrepancy": money(discrepancy) if discrepancy is not None else None,
        "formula": "sum × rate / 100 × days / 365" if basis == "annual" else "sum × rate / 100",
        "warnings": list(dict.fromkeys(warnings)),
        "indicators": used,
        "applied_metrics": sorted(applied_metrics) if kind != "normative" else [],
    }


def valuation(inputs, today=None, exchange=None, policy=None):
    today = today or date.today()
    exchange = exchange or {}
    policy = policy or {}
    low = D(str(policy.get("valuation_outlier_low", "0.5")))
    high = D(str(policy.get("valuation_outlier_high", "1.5")))
    tolerance = D(str(policy.get("valuation_tolerance", "0.15")))
    large_limit = policy.get("large_object_threshold")
    require_appraiser = inputs.get("object_type") == "large" or (
        large_limit is not None and D(str(inputs["object_value"])) >= D(str(large_limit))
    )
    eligible, rejected = [], []
    for c in inputs.get("comparables", []):
        age = (today - date.fromisoformat(str(c["date"]))).days
        # Six calendar months, not an approximate fixed number of days.
        month = today.month - 6
        year = today.year
        if month <= 0:
            month += 12
            year -= 1
        import calendar

        cutoff = date(year, month, min(today.day, calendar.monthrange(year, month)[1]))
        reason = None
        if not c.get("same_item", True):
            reason = "другое изделие"
        elif age < 0 or date.fromisoformat(str(c["date"])) < cutoff:
            reason = "дата вне последних 6 месяцев"
        elif D(str(c["price"])) <= 0:
            reason = "нет положительной цены"
        currency = c.get("currency", "UZS")
        fx = D(1) if currency == "UZS" else D(str(exchange.get(currency, {}).get("value", 0)))
        if not fx:
            reason = "курс валюты недоступен"
        if (
            c.get("original_price") is not None
            and D(str(c["original_price"])) != D(str(c["price"]))
            and not c.get("edit_reason")
        ):
            reason = "нет причины правки цены"
        item = {
            **c,
            "price_uzs": money(D(str(c["price"])) * fx),
            "original_uzs": money(D(str(c.get("original_price") or c["price"])) * fx),
        }
        if currency != "UZS":
            item["exchange_source"] = exchange.get(currency)
        if reason:
            rejected.append({**item, "reason": reason})
        else:
            eligible.append(item)
    raw_median = median([D(c["original_uzs"]) for c in eligible]) if eligible else None
    center = median([D(c["price_uzs"]) for c in eligible]) if eligible else None
    kept = []
    for c in eligible:
        if len(eligible) >= 3 and (D(c["price_uzs"]) < center * low or D(c["price_uzs"]) > center * high):
            rejected.append({**c, "reason": f"выброс: вне {low * 100}–{high * 100}% медианы"})
        else:
            kept.append(c)
    estimate, method = None, "unavailable"
    if not require_appraiser and inputs.get("object_type") == "equipment" and inputs.get("purchase_price"):
        estimate = D(str(inputs["purchase_price"])) * (
            1 - D(str(inputs.get("depreciation_percent", 0))) / 100
        )
        method = "purchase_less_depreciation"
    elif require_appraiser:
        if all(
            inputs.get(k)
            for k in [
                "appraiser_value",
                "appraiser_source",
                "appraiser_date",
                "second_method_value",
                "second_method_source",
                "second_method_date",
            ]
        ):
            if any(
                date.fromisoformat(str(inputs[k])) > today for k in ["appraiser_date", "second_method_date"]
            ):
                raise ValueError("Дата оценки не может быть в будущем")
            estimate, method = D(str(inputs["appraiser_value"])), "appraiser_and_second_method"
    elif kept:
        estimate = sum(D(c["price_uzs"]) for c in kept) / len(kept)
        method = "comparable_mean"
    deviation = abs(D(str(inputs["object_value"])) - estimate) / estimate if estimate else None
    second_deviation = (
        abs(D(str(inputs["second_method_value"])) - estimate) / estimate
        if method == "appraiser_and_second_method" and estimate
        else None
    )
    evidence_missing = []
    if method == "purchase_less_depreciation":
        evidence_missing = [key for key in ("purchase_source", "purchase_date") if not inputs.get(key)]
    confirmed = (
        deviation is not None
        and deviation <= tolerance
        and (second_deviation is None or second_deviation <= tolerance)
        and not evidence_missing
    )
    return {
        "method": method,
        "estimate": money(estimate) if estimate is not None else None,
        "raw_median": money(raw_median) if raw_median is not None else None,
        "minimum": min((c["price_uzs"] for c in kept), key=D, default=None),
        "maximum": max((c["price_uzs"] for c in kept), key=D, default=None),
        "deviation_percent": number(deviation * 100) if deviation is not None else None,
        "second_method_deviation_percent": number(second_deviation * 100)
        if second_deviation is not None
        else None,
        "status": "unavailable" if estimate is None else "confirmed" if confirmed else "clarify",
        "comparables": kept,
        "rejected": rejected,
        "evidence_missing": evidence_missing,
        "method_note": "Правило оценки утверждено актуарием"
        if policy.get("approved_by")
        else "Правило оценки — экспертное, не утверждено страховщиком",
        "policy": {
            "outlier_low": str(low),
            "outlier_high": str(high),
            "tolerance": str(tolerance),
            "requires_appraiser": bool(require_appraiser),
            "template_id": policy.get("id"),
            "approved_by": policy.get("approved_by"),
        },
    }


def loss_summary(rows):
    result = []
    for row in sorted(rows, key=lambda x: x["year"]):
        premiums, contracts = row.get("premiums"), row.get("contracts")
        result.append(
            {
                **row,
                "loss_ratio": number(D(row["payments"]) / D(premiums)) if premiums and D(premiums) else None,
                "frequency": number(D(row["claims"]) / D(contracts)) if contracts else None,
            }
        )
    return result
