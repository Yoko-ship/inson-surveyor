import io
import json
from pathlib import Path
from xml.sax.saxutils import escape

from docx import Document
from docx.shared import Pt
from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

from surveyor.config import settings

LABELS = {
    "ru": [
        "Сюрвейерский акт",
        "1. Объект и документы",
        "2. Оценка стоимости",
        "3. Тариф и страховая премия",
        "4. Аналитика риска",
        "5. Заключение и оговорки",
        "Данные недоступны",
        "Подлежит подтверждению андеррайтером · Не является кредитным скорингом",
    ],
    "uz": [
        "Syurveyer dalolatnomasi",
        "1. Obyekt va hujjatlar",
        "2. Qiymatni baholash",
        "3. Tarif va sug‘urta mukofoti",
        "4. Xatar tahlili",
        "5. Xulosa va shartlar",
        "Ma’lumot mavjud emas",
        "Anderrayter tasdig‘i talab qilinadi · Kredit skoringi emas",
    ],
    "en": [
        "Survey report",
        "1. Object and documents",
        "2. Property valuation",
        "3. Rate and insurance premium",
        "4. Risk analysis",
        "5. Conclusion and clauses",
        "Data unavailable",
        "Subject to underwriter confirmation · Not a credit score",
    ],
}
FIELD_LABELS = {
    "insured_sum": "Страховая сумма / Insured sum",
    "object_value": "Стоимость объекта / Object value",
    "region": "Регион / Region",
    "term_days": "Срок, дней / Term, days",
    "object_description": "Объект / Object",
    "minimum_rate": "Минимальная ставка, % / Minimum rate",
    "recommended_rate": "Рекомендуемая ставка, % / Recommended rate",
    "annualized_rate": "Годовой эквивалент, % / Annual equivalent",
    "annual_market_rate": "Рыночная годовая ставка, % / Annual market rate",
    "premium": "Премия, UZS / Premium",
    "formula": "Формула / Formula",
    "rate_type": "Тип ставки / Rate type",
    "premium_discrepancy": "Отклонение премии документа, UZS / Premium difference",
    "comparison": "Сверка тарифа / Comparison",
    "risk_score": "Страховой балл / Insurance score",
    "risk_level": "Уровень риска / Risk level",
    "risk_multiplier": "Множитель риска / Risk multiplier",
    "regional_adjustment": "Поправка региона / Regional adjustment",
    "loss_adjustment": "Поправка убытков / Claims adjustment",
    "estimate": "Оценка, UZS / Estimate",
    "raw_median": "Медиана до правок, UZS / Original median",
    "method": "Метод / Method",
    "deviation_percent": "Отклонение, % / Deviation",
    "status": "Статус / Status",
}


def display(value, missing):
    if value is None or value == "":
        return missing
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, indent=2)
    return str(value)


def sections(report):
    s = report.snapshot
    labels = LABELS[s["language"]]
    missing = labels[6]

    def pairs(data, keys):
        return [f"{FIELD_LABELS.get(k, k)}: {display(data.get(k), missing)}" for k in keys]

    object_lines = [
        s["title"],
        f"ID: {report.id}",
        f"Дата / Date: {report.created_at.isoformat()}",
        f"Автор / Author: {s['author']['name']}",
    ]
    object_lines += pairs(
        s["inputs"], ["insured_sum", "object_value", "region", "term_days", "object_description"]
    )
    object_lines.append("Источник полей / Field source: ручной ввод сотрудника / employee input")
    for doc in s["documents"]:
        object_lines += [
            f"Документ / Document: {doc['filename']} · SHA256 {doc['sha256']}",
            display(doc["extracted"], missing),
        ]
    object_lines += [
        "Правки / Corrections: " + display(s["inputs"].get("overrides"), missing),
        "Причина / Reason: " + display(s["inputs"].get("override_reason"), missing),
        "Расхождения / Conflicts: " + display(s["conflicts"], missing),
    ]
    v = s["valuation"]
    value_lines = pairs(v, ["method", "estimate", "raw_median", "deviation_percent", "status"])
    value_lines += [
        display(v["comparables"], missing),
        "Исключено / Excluded: " + display(v["rejected"], missing),
        v["method_note"],
    ]
    for k in [
        "purchase_price",
        "depreciation_percent",
        "appraiser_value",
        "appraiser_source",
        "appraiser_date",
        "second_method_value",
        "second_method_source",
        "second_method_date",
    ]:
        if s["inputs"].get(k):
            value_lines.append(f"{k}: {s['inputs'][k]}")
    c = s["calculation"]
    rate_lines = [
        f"Продукт / Product: {s['product']['code']} — {s['product']['name']}",
        f"Источник / Source: тарифная политика; версия {s['product']['version_id']}; действует с {s['product']['effective_from']}",
    ]
    rate_lines += pairs(
        c,
        [
            "rate_type",
            "minimum_rate",
            "recommended_rate",
            "annualized_rate",
            "annual_market_rate",
            "premium",
            "formula",
            "premium_discrepancy",
            "comparison",
        ],
    )
    if c.get("reason"):
        rate_lines.append(c["reason"])
    risk_lines = pairs(
        c, ["risk_score", "risk_level", "risk_multiplier", "regional_adjustment", "loss_adjustment"]
    )
    risk_lines += c.get("warnings", [])
    risk_lines += [
        "Убытки за три полных года / Claims for three complete years: " + display(s["losses"], missing)
    ]
    if s.get("calibration"):
        risk_lines.append(
            "Утверждённая калибровка / Approved calibration: " + display(s["calibration"], missing)
        )
    if s.get("template"):
        risk_lines.append("Шаблон / Template: " + display(s["template"], missing))
    for indicator in s["indicators"]:
        risk_lines.append(
            f"{indicator['metric']}: {indicator['value']} {indicator['unit']} · {indicator['period']} · {indicator['source_url']} · {indicator['fetched_at']}"
            + (" · УСТАРЕЛИ / STALE" if indicator["stale"] else "")
        )
    return labels, [
        (labels[1], object_lines),
        (labels[2], value_lines),
        (labels[3], rate_lines),
        (labels[4], risk_lines),
        (labels[5], s["disclaimers"] + s["clauses"] + s["checklist"]),
    ]


def export_docx(report):
    labels, blocks = sections(report)
    doc = Document()
    doc.styles["Normal"].font.name = "Arial"
    doc.styles["Normal"].font.size = Pt(10)
    doc.add_heading(labels[0], 0)
    for title, lines in blocks:
        doc.add_heading(title, 1)
        for line in lines:
            doc.add_paragraph(line)
    doc.sections[0].footer.paragraphs[0].text = labels[7]
    buffer = io.BytesIO()
    doc.save(buffer)
    return buffer.getvalue()


def export_pdf(report):
    labels, blocks = sections(report)
    candidates = [
        settings.pdf_font_path,
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/System/Library/Fonts/Supplemental/Arial.ttf",
    ]
    font_path = next((p for p in candidates if p and Path(p).is_file()), None)
    if not font_path:
        raise ValueError("Установите шрифт DejaVu Sans или задайте PDF_FONT_PATH")
    if "Surveyor" not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(TTFont("Surveyor", font_path))
    body = ParagraphStyle("BodyRu", fontName="Surveyor", fontSize=9, leading=13, spaceAfter=6, wordWrap="CJK")
    heading = ParagraphStyle(
        "HeadRu",
        parent=body,
        fontSize=14,
        leading=19,
        textColor=colors.HexColor("#17463e"),
        spaceBefore=15,
        spaceAfter=10,
    )
    buffer = io.BytesIO()
    pdf = SimpleDocTemplate(
        buffer, topMargin=18 * mm, bottomMargin=22 * mm, rightMargin=18 * mm, leftMargin=18 * mm
    )
    story = [Paragraph(escape(labels[0]), heading)]
    for title, lines in blocks:
        story.append(Paragraph(escape(title), heading))
        for line in lines:
            story.append(Paragraph(escape(line).replace("\n", "<br/>"), body))
        story.append(Spacer(1, 5 * mm))

    def footer(canvas, doc):
        canvas.setFont("Surveyor", 7)
        canvas.drawString(18 * mm, 12 * mm, labels[7])
        canvas.drawRightString(190 * mm, 8 * mm, str(doc.page))

    pdf.build(story, onFirstPage=footer, onLaterPages=footer)
    return buffer.getvalue()
