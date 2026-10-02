from datetime import date
from decimal import Decimal, InvalidOperation

from fastapi import HTTPException
from sqlalchemy import select

from surveyor.calculations import calculate, loss_summary, valuation
from surveyor.db import Calibration, ClassTemplate, Document, Loss, Product, Report, Survey, audit
from surveyor.document_values import derive_document_term
from surveyor.reserves import classify_rnp
from surveyor.sources import latest_indicators


def survey_for(db, survey_id, user, write=False):
    row = db.get(Survey, survey_id)
    if not row or (
        row.owner_id != user.id and (write or user.role not in {"admin", "underwriter", "actuary"})
    ):
        raise HTTPException(404, "Осмотр не найден")
    return row


def product_for(db, code, when=None):
    row = db.scalar(
        select(Product)
        .where(Product.code == code, Product.effective_from <= (when or date.today()))
        .order_by(Product.effective_from.desc())
    )
    if not row:
        raise HTTPException(422, "Продукт не действует на выбранную дату")
    return row


def context_for(db, inputs):
    product = product_for(db, inputs["product_code"], date.fromisoformat(inputs["tariff_date"]))
    template = db.scalar(
        select(ClassTemplate)
        .where(ClassTemplate.class_code == product.data["class_code"])
        .order_by(ClassTemplate.created_at.desc())
    )
    template_data = (
        {
            **template.data,
            "id": template.id,
            "approved_by": template.approved_by,
            "approved_at": template.approved_at.isoformat() if template.approved_at else None,
        }
        if template
        else None
    )
    from surveyor.factor_pricing import calibration_stale, validate_answers

    if template_data:
        template_data["factor_calibration_stale"] = calibration_stale(db, template_data)
    validate_answers(inputs, template_data)
    indicators = latest_indicators(db, inputs["region"], product.data["class_code"])
    calibration = db.scalar(
        select(Calibration)
        .where(Calibration.product_code == product.code)
        .order_by(Calibration.created_at.desc())
    )
    loss_rows = db.scalars(
        select(Loss).where(
            Loss.product_code == product.code,
            Loss.year >= date.today().year - 3,
            Loss.year < date.today().year,
        )
    ).all()
    losses = loss_summary([r.data for r in loss_rows])
    calibration_data = None
    if calibration:
        # Editing claims invalidates a calibration based on an older dataset.
        if calibration.data["losses"] == losses:
            calibration_data = {
                **calibration.data,
                "approved_by": calibration.approved_by,
                "id": calibration.id,
            }
    calc = calculate(product.data, inputs, template_data, indicators, calibration_data)
    return product, template_data, indicators, losses, calibration_data, calc


def validate_borrower_document(db, survey_id, inputs):
    borrower = inputs.get("borrower")
    if borrower:
        doc = db.get(Document, borrower["document_id"])
        if not doc or doc.survey_id != survey_id:
            raise HTTPException(422, "Выберите отчёт кредитного бюро, загруженный в этот осмотр")


def build_report(db, survey, user):
    inputs = survey.inputs
    if not inputs or not inputs.get("manual_review_confirmed"):
        raise HTTPException(422, "Проверьте данные и подтвердите ручную проверку")
    validate_borrower_document(db, survey.id, inputs)
    product, template, indicators, losses, calibration, calc = context_for(db, inputs)
    docs = db.scalars(select(Document).where(Document.survey_id == survey.id)).all()
    documents = [
        {"id": d.id, "filename": d.filename, "sha256": d.sha256, "extracted": d.extracted} for d in docs
    ]
    sources = {}
    conflicts = []
    for document in documents:
        for field, item in document["extracted"]["fields"].items():
            if item.get("value") is not None:
                sources.setdefault(field, []).append(item)
        date_fields = {
            key: item
            for key, item in document["extracted"]["fields"].items()
            if key in {"contract_start", "contract_end"}
        }
        derive_document_term(date_fields, document["filename"])
        derived = date_fields.get("term_days", {})
        if derived.get("value") is not None:
            sources.setdefault("term_days", []).append(derived)
    for field, values in sources.items():

        def comparable_value(value):
            try:
                return Decimal(str(value))
            except InvalidOperation:
                return str(value).strip()

        distinct = {comparable_value(x["value"]) for x in values}
        entered = inputs.get(field)
        if len(distinct) > 1 or (entered is not None and comparable_value(entered) not in distinct):
            conflicts.append(
                {
                    "field": field,
                    "sources": values,
                    "entered": entered,
                    "message": "Расхождение источников / ручного ввода",
                }
            )
    fx = {
        d["metric"].removeprefix("fx_"): d
        for d in indicators
        if d["metric"].startswith("fx_") and not d["stale"]
    }
    from surveyor.db import PublicReference
    from surveyor.references import reference_view

    references = []
    for reference_id in inputs.get("reference_ids", []):
        row = db.get(PublicReference, reference_id)
        if not row:
            raise HTTPException(422, "Источник не найден")
        references.append(reference_view(row))
    snapshot = {
        "references": references,
        "version": 1,
        "title": survey.title,
        "survey_revision": survey.revision,
        "language": inputs.get("language", "ru"),
        "author": {"name": user.name, "branch": user.branch, "id": user.id},
        "inputs": inputs,
        "product": {**product.data, "version_id": product.id},
        "rnp_classification": classify_rnp(inputs["rnp_context"]) if inputs.get("rnp_context") else None,
        "template": template,
        "calculation": calc,
        "valuation": valuation(inputs, exchange=fx, policy=template),
        "documents": documents,
        "assistance": assistance_snapshot(db, survey),
        "conflicts": conflicts,
        "indicators": [i for i in indicators if i.get("subject", "market") in {"market", '"INSON" AJ'}],
        "losses": losses,
        "calibration": calibration,
        "clauses": (template or {})
        .get("clauses_translations", {})
        .get(inputs.get("language", "ru"), (template or {}).get("clauses", [])),
        "disclaimers": [
            "Подлежит подтверждению андеррайтером",
            "Не является кредитным скорингом",
            "Значения документов проверены сотрудником; предложения ИИ требуют ручного подтверждения",
        ],
        "checklist": [
            "Проверить суммы, сроки и источники",
            "Разрешить расхождения документов",
            "Проверить оценку стоимости",
            "Проверить актуальность тарифов и нормативных актов",
            "Утвердить условия андеррайтером",
        ],
    }
    report = Report(survey_id=survey.id, snapshot=snapshot)
    db.add(report)
    survey.status = "review"
    db.flush()
    audit(db, user, "report.created", report.id, {"survey_id": survey.id, "revision": survey.revision})
    db.commit()
    return report


def assistance_snapshot(db, survey):
    from surveyor.inspection_assistant import guidance

    guide = guidance(db, survey)
    return {
        "answers": (survey.assistance or {}).get("answers", {}),
        "question_labels": (survey.assistance or {}).get("question_labels", {}),
        "reviews": [
            {
                **r,
                "stale": r["basis_hash"] != guide["basis_hash"]
                or r.get("context_hash") != guide["context_hash"],
            }
            for r in (survey.assistance or {}).get("reviews", [])
        ],
    }
