"""PDF table/prose factor catalogue, pricing evidence and segmented calibration.

Numerical values never come from the PDF or an AI. Statistical estimates are
univariate pure-premium relativities, proposed for explicit actuarial review.
"""

import hashlib
import json
from datetime import date
from decimal import Decimal, localcontext
from functools import lru_cache
from pathlib import Path

from sqlalchemy import select

from surveyor.db import ImportBatch

D = Decimal
METHOD = "segmented-pure-premium-v1"


@lru_cache(maxsize=1)
def catalogue():
    source = json.loads(
        (Path(__file__).parent / "policies/tariff-factors-2026-10-02.json").read_text(encoding="utf-8")
    )
    notes = json.loads((Path(__file__).parent / "policies/factor-notes.json").read_text(encoding="utf-8"))
    return {**source, "entries": [*source["entries"], *notes]}


def entries(insurance_class):
    return [r for r in catalogue()["entries"] if not r["classes"] or insurance_class in r["classes"]]


def validate_policy(policy):
    available = {r["id"]: r for r in entries(policy.insurance_class)}
    for key, values in policy.coefficients.items():
        if key not in available:
            raise ValueError("Фактор не относится к выбранному классу")
        for side in ("raises", "lowers"):
            if getattr(values, side) is not None and available[key][side] == "—":
                raise ValueError("В документе нет этого направления влияния фактора")


def validate_class(class_code, insurance_class):
    if class_code.isdigit() and 1 <= int(class_code) <= 18 and int(class_code) != insurance_class:
        raise ValueError("Класс факторов должен совпадать с номером страхового класса шаблона")


def validate_answers(inputs, template):
    answers = inputs.get("factor_answers", {})
    policy = (template or {}).get("factor_policy")
    if answers and not policy:
        raise ValueError("Для ответов по факторам нужен шаблон с факторным расчётом")
    available = {r["id"]: r for r in entries(policy["insurance_class"])} if policy else {}
    if set(answers) - set(available):
        raise ValueError("Ответы содержат факторы другого класса; проверьте выбранный продукт")
    for key, answer in answers.items():
        choice = answer["choice"]
        if choice in {"raises", "lowers"} and available[key][choice] == "—":
            raise ValueError("Выбранное направление отсутствует в документе")


def factor_result(inputs, template, normative=False):
    policy = (template or {}).get("factor_policy")
    if not policy:
        return None
    validate_answers(inputs, template)
    approved = bool(template.get("approved_by"))
    stale = bool(template.get("factor_calibration_stale"))
    active = approved and not stale and not normative
    rows, clarify = [], []
    with localcontext() as ctx:
        ctx.prec = 512
        proposed = D(1)
        for entry in entries(policy["insurance_class"]):
            answer = inputs.get("factor_answers", {}).get(entry["id"], {})
            choice = answer.get("choice", "unanswered")
            coefficient = policy["coefficients"].get(entry["id"], {}).get(choice)
            if choice in {"neutral", "not_applicable"}:
                coefficient = "1"
            reason = (
                "unanswered"
                if choice == "unanswered"
                else "coefficient_missing"
                if coefficient is None
                else None
            )
            if reason:
                clarify.append({"id": entry["id"], "label": entry["label"], "reason": reason})
            if coefficient is not None:
                proposed *= D(coefficient)
            rows.append(
                {
                    "id": entry["id"],
                    "label": entry["label"],
                    "section": entry["section"],
                    "page": entry["page"],
                    "choice": choice,
                    "evidence": answer.get("evidence", ""),
                    "source_condition": entry.get(choice, ""),
                    "coefficient": coefficient,
                    "applied_coefficient": coefficient if active and coefficient is not None else "1",
                }
            )
        applied = proposed if active else D(1)
    return {
        "source_id": catalogue()["id"],
        "source_sha256": catalogue()["sha256"],
        "template_id": template.get("id"),
        "insurance_class": policy["insurance_class"],
        "status": "statutory"
        if normative
        else "stale"
        if stale
        else "approved"
        if approved
        else "unapproved",
        "calibration_status": "statistical_proposal"
        if template.get("factor_calibration")
        else "uncalibrated",
        "approved_by": template.get("approved_by"),
        "approved_at": template.get("approved_at"),
        "rationale": policy["rationale"],
        "multiplier": str(applied),
        "proposed_multiplier": str(proposed),
        "rows": rows,
        "clarify": clarify,
        "calibration": template.get("factor_calibration"),
        "ready_for_underwriting": normative or (active and not clarify),
    }


def experience_hash(rows):
    return hashlib.sha256(json.dumps(rows, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def latest_experience(db, class_code):
    # JSON portability: filtering a small list works identically on SQLite/PostgreSQL.
    return next(
        (
            r
            for r in db.scalars(
                select(ImportBatch)
                .where(ImportBatch.kind == "factor_experience", ImportBatch.consumed.is_(True))
                .order_by(ImportBatch.created_at.desc(), ImportBatch.id.desc())
            )
            if r.data["class_code"] == class_code
        ),
        None,
    )


def calibration_stale(db, template):
    calibration = template.get("factor_calibration")
    if not calibration:
        return False
    latest = latest_experience(db, template["class_code"])
    return not latest or latest.data["sha256"] != calibration["data_sha256"]


def propose(policy, rows, minimum_exposure, max_change):
    """Ratio of paid losses per insured-year versus neutral, with credibility bounds.

    Each factor/choice must have the same most recent 3–5 completed years. This is
    not multivariate causal inference. Correlation and incurred-loss development
    require actuarial review; direction conflicts are rejected, never inverted.
    """
    import copy

    result = copy.deepcopy(policy)
    estimates = []
    available = {r["id"]: r for r in entries(policy["insurance_class"])}
    for factor_id in sorted({r["factor_id"] for r in rows}):
        if factor_id not in available:
            raise ValueError("Статистика содержит фактор другого класса")
        segments = {}
        for row in rows:
            if row["factor_id"] == factor_id:
                segments.setdefault(row["choice"], []).append(row)
        if "neutral" not in segments or not (set(segments) & {"raises", "lowers"}):
            raise ValueError("Для каждого фактора нужны нейтральный сегмент и повышающий/понижающий")
        years = {r["year"] for r in segments["neutral"]}
        if len(years) not in {3, 4, 5} or years != set(
            range(date.today().year - len(years), date.today().year)
        ):
            raise ValueError("Нужны последние 3–5 полных последовательных лет")
        costs = {}
        for choice, group in segments.items():
            if len(group) != len(years) or {r["year"] for r in group} != years:
                raise ValueError("Сегменты должны охватывать одинаковые годы без повторов")
            exposure = sum(D(r["exposure"]) for r in group)
            if exposure < minimum_exposure:
                raise ValueError("Недостаточно экспозиции для выбранного порога достоверности")
            costs[choice] = sum(D(r["payments"]) for r in group) / exposure
        if costs["neutral"] <= 0:
            raise ValueError("Нейтральный сегмент должен иметь положительные выплаты")
        for choice in sorted(set(costs) - {"neutral"}):
            if available[factor_id][choice] == "—":
                raise ValueError("В документе отсутствует это направление")
            raw = costs[choice] / costs["neutral"]
            if (choice == "raises" and raw <= 1) or (choice == "lowers" and raw >= 1):
                raise ValueError(
                    "Статистика противоречит направлению PDF; требуется отдельный анализ актуария"
                )
            estimate = max(D("0.1"), min(D(10), max(1 - max_change, min(1 + max_change, raw))))
            value = str(estimate.quantize(D("0.00000001")))
            result["coefficients"].setdefault(factor_id, {})[choice] = value
            estimates.append(
                {
                    "factor_id": factor_id,
                    "choice": choice,
                    "raw": str(raw),
                    "coefficient": value,
                    "years": sorted(years),
                    "neutral_cost": str(costs["neutral"]),
                    "segment_cost": str(costs[choice]),
                }
            )
    return result, estimates
