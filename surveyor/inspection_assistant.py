"""Grounded comparison, guided questions and human-reviewed photo observations."""

import copy
import hashlib
import json
import tempfile
from pathlib import Path
from typing import Literal

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select

from surveyor import ai_config, ai_providers, codex_documents
from surveyor.db import Document
from surveyor.inspection_ai import checked_bytes
from surveyor.services import context_for


class Citation(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    source_id: str = Field(max_length=100)
    quote: str = Field(max_length=2000)


class Finding(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    category: Literal["contradiction", "missing", "evidence", "risk"]
    text: str = Field(min_length=1, max_length=1500)
    citations: list[Citation] = Field(min_length=1, max_length=5)


class ReviewAnalysis(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    findings: list[Finding] = Field(max_length=20)
    questions: list[str] = Field(max_length=15)
    explanation: list[Finding] = Field(max_length=10)


def documents_for(db, survey):
    return list(db.scalars(select(Document).where(Document.survey_id == survey.id).order_by(Document.id)))


def context_hash(context):
    return hashlib.sha256(json.dumps(context, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def basis_hash(survey, docs):
    # Confirmation/language changes do not invalidate evidence; facts and answers do.
    inputs = {
        k: v
        for k, v in survey.inputs.items()
        if k not in {"manual_review_confirmed", "language", "override_reason", "overrides"}
    }
    data = {
        "inputs": inputs,
        "answers": (survey.assistance or {}).get("answers", {}),
        "documents": [{"id": d.id, "sha256": d.sha256, "extracted": d.extracted} for d in docs],
    }
    return hashlib.sha256(json.dumps(data, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def guidance(db, survey):
    docs = documents_for(db, survey)
    inputs = survey.inputs
    questions = [
        {"id": "ownership", "text": "Какие документы подтверждают право на объект?", "kind": "document"},
        {
            "id": "loss_history",
            "text": "Какие убытки были за последние 3–5 лет? Укажите источник.",
            "kind": "evidence",
        },
    ]
    if not any(d.extracted.get("kind") == "contract" for d in docs):
        questions.append(
            {
                "id": "contract",
                "text": "Добавьте договор или поясните, почему он пока отсутствует.",
                "kind": "document",
            }
        )
    views = {
        "vehicle": ["Общий вид с четырёх сторон", "VIN и показания одометра", "Повреждения крупным планом"],
        "equipment": [
            "Общий вид оборудования",
            "Заводская табличка и серийный номер",
            "Панель управления и защитные устройства",
        ],
        "housing": [
            "Фасад и крыша",
            "Электрощит и проводка",
            "Пожарная защита",
            "Следы протечек и повреждений",
        ],
        "large": [
            "Общий вид и территория",
            "Пожарная защита",
            "Электрооборудование",
            "Несущие конструкции и повреждения",
        ],
        "other": ["Общий вид объекта", "Идентификационные признаки", "Повреждения и защитные устройства"],
    }
    object_type = inputs.get("object_type", "other")
    for i, text in enumerate(views[object_type]):
        questions.append({"id": f"photo_{object_type}_{i}", "text": text, "kind": "photo"})
    if object_type == "large":
        questions.append(
            {
                "id": "valuation",
                "text": "Укажите отчёт оценщика и независимый второй метод оценки.",
                "kind": "document",
            }
        )
    explanation, context = [], {}
    if inputs.get("product_code") and inputs.get("insured_sum") and inputs.get("object_value"):
        try:
            product, template, indicators, losses, calibration, calc = context_for(db, inputs)
            context = {
                "product": {**product.data, "version_id": product.id},
                "template": template,
                "indicators": indicators,
                "losses": losses,
                "calibration": calibration,
                "calculation": calc,
            }
            explanation = [
                {"field": k, "value": v, "source": "calculation"}
                for k, v in calc.items()
                if k
                in {
                    "base_rate",
                    "minimum_rate",
                    "recommended_rate",
                    "premium",
                    "formula",
                    "risk_level",
                    "regional_adjustment",
                    "loss_adjustment",
                    "warnings",
                }
            ]
            if calc.get("factor_pricing"):
                factors = calc["factor_pricing"]
                explanation.append(
                    {"field": "factor_multiplier", "value": factors["multiplier"], "source": "calculation"}
                )
                questions += [
                    {"id": "factor_" + r["id"], "text": "Уточните фактор: " + r["label"], "kind": "evidence"}
                    for r in factors["clarify"]
                ]
            questions.append(
                {
                    "id": "class_evidence",
                    "text": f"Подтвердите риски класса {product.data['class_code']} и выбранные признаки риска документами.",
                    "kind": "evidence",
                }
            )
            if not product.data.get("policy_current_confirmed"):
                questions.append(
                    {
                        "id": "tariff_approval",
                        "text": "Подтвердите актуальность тарифа и основание его применения.",
                        "kind": "approval",
                    }
                )
            for key in (template or {}).get("feature_weights", {}):
                questions.append({"id": f"feature_{key}", "text": key, "kind": "risk"})
        except (HTTPException, ValueError, KeyError) as exc:
            context = {
                "unavailable": "Расчёт недоступен: проверьте продукт, дату и исходные данные.",
                "error_type": type(exc).__name__,
            }
    else:
        questions.append(
            {
                "id": "inputs",
                "text": "Сохраните продукт, регион, суммы и срок для объяснения расчёта.",
                "kind": "input",
            }
        )
    conflicts = []
    for key in {key for d in docs for key in d.extracted.get("fields", {})}:
        values = [
            {"document_id": d.id, "filename": d.filename, **d.extracted["fields"][key]}
            for d in docs
            if d.extracted.get("fields", {}).get(key, {}).get("value") is not None
        ]
        distinct = {str(v["value"]) for v in values}
        if len(distinct) > 1 or (
            key in inputs and inputs[key] is not None and distinct and str(inputs[key]) not in distinct
        ):
            conflicts.append({"field": key, "values": values, "entered": inputs.get(key)})
            questions.append(
                {
                    "id": f"conflict_{key}",
                    "text": f"Разрешите расхождение: {key}. Укажите выбранное значение и источник.",
                    "kind": "conflict",
                }
            )
    return {
        "questions": questions,
        "answers": (survey.assistance or {}).get("answers", {}),
        "conflicts": conflicts,
        "explanation": explanation,
        "context": context,
        "basis_hash": basis_hash(survey, docs),
        "context_hash": context_hash(context),
    }


def analyze(db, survey, selected_ids, kind, config, locale):
    docs = [d for d in documents_for(db, survey) if d.id in selected_ids]
    if len(docs) != len(selected_ids):
        raise ValueError("Документы осмотра изменились.")
    guide = guidance(db, survey)
    sources, images = [], []
    with tempfile.TemporaryDirectory(prefix="surveyor-assistant-") as tmp:
        root = Path(tmp)
        for doc in docs:
            folder = root / doc.id
            folder.mkdir()
            text, pages = codex_documents.prepare(checked_bytes(doc), doc.filename, folder, config.limits)
            is_photo = Path(doc.filename).suffix.lower() in {".jpg", ".jpeg", ".png", ".webp"}
            if kind == "photo" and not is_photo:
                raise ValueError("Для оценки видимых условий выберите только фотографии.")
            sources.append(
                {
                    "id": doc.id,
                    "filename": doc.filename,
                    "text": text,
                    "reviewed_fields": doc.extracted.get("fields", {}),
                    "image_indices": list(range(len(images) + 1, len(images) + len(pages) + 1)),
                    "visual": bool(pages),
                    "sha256": doc.sha256,
                }
            )
            images.extend(pages)
        if kind == "inspection":
            context = copy.deepcopy(guide["context"])
            if "indicators" in context:
                # The public catalogue can dwarf the uploaded documents. Explain
                # only the observations actually selected by the calculation;
                # retain the complete context in the review snapshot below.
                available = len(context["indicators"])
                context["indicators"] = context["calculation"]["indicators"]
                context["indicator_scope"] = {
                    "description": "Only observations used by the deterministic calculation are supplied. Do not infer omitted observations.",
                    "available_count": available,
                    "included_count": len(context["indicators"]),
                }
            # Aggregate experience stays in the immutable review, not in model input.
            # Coefficient estimates, method and hashes are sufficient to explain pricing.
            for calibration in [
                (context.get("template") or {}).get("factor_calibration"),
                (context.get("calculation", {}).get("factor_pricing") or {}).get("calibration"),
            ]:
                if calibration and "rows" in calibration:
                    calibration["experience_rows_omitted"] = len(calibration.pop("rows", []))
            for key, value in {
                "inputs": survey.inputs,
                "answers": guide["answers"],
                **context,
            }.items():
                sources.append(
                    {
                        "id": key,
                        "text": json.dumps(value, ensure_ascii=False, sort_keys=True),
                        "visual": False,
                    }
                )
        payload = json.dumps({"sources": sources, "task": kind}, ensure_ascii=False)
        db.commit()
        result = ai_providers.structured(
            config,
            ai_config.trusted_instructions(config, locale, kind),
            payload,
            images,
            root,
            ReviewAnalysis,
        )
    allowed = {s["id"]: s for s in sources}
    rejected = 0
    for section in ("findings", "explanation"):
        validated = []
        for row in result[section]:
            good = kind != "photo" or section != "explanation"
            citations = []
            for cite in row["citations"]:
                source = allowed.get(cite["source_id"])
                if not source:
                    good = False
                    continue
                quote = cite["quote"].strip()
                # Text evidence requires exact quotes; images remain visibly unverified.
                found = bool(quote and quote in source["text"])
                if not found and not source["visual"]:
                    good = False
                citations.append(
                    {
                        **cite,
                        "quote_found_in_text": found,
                        "filename": source.get("filename"),
                        "sha256": source.get("sha256"),
                    }
                )
            if good:
                validated.append({**row, "id": f"{section}_{len(validated)}", "citations": citations})
            else:
                rejected += 1
        result[section] = validated
    result["questions"] = [q for q in result["questions"] if 0 < len(q) <= 1000]
    return {
        **result,
        "rejected_citations": rejected,
        "basis_hash": guide["basis_hash"],
        "context": guide["context"],
        "context_hash": guide["context_hash"],
        "display_mode": config.display_mode,
        "source_ids": selected_ids,
        "provider": config.provider,
        "model": getattr(config, config.provider).model or "provider_default",
        "config_revision": ai_config.digest(config),
    }
