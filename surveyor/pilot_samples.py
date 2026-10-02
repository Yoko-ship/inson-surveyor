"""Invented, immutable inputs for the personal Codex pilot; no company documents."""

from io import BytesIO

from PIL import Image, ImageDraw, ImageFont

FIELDS = (
    "insured_sum",
    "object_value",
    "declared_rate",
    "declared_premium",
    "term_days",
    "object_description",
    "insured_organization",
    "insurer_organization",
    "contract_start",
    "contract_end",
)
SAMPLES = {
    "text": {
        "title": "Учебный договор · текст",
        "text": (
            "УЧЕБНЫЙ ДОГОВОР — ВСЕ ДАННЫЕ ВЫМЫШЛЕНЫ\n"
            "Страхователь: ООО Тестовый объект\n"
            "Страховщик: АО Учебное страхование\n"
            "Объект страхования: Учебный станок\n"
            "Стоимость объекта: 125 000 000 сум\n"
            "Страховая сумма: 100 000 000 сум\n"
            "Тариф: 0,5%\n"
            "Страховая премия: 500 000 сум\n"
            "Дата начала: 2026-01-01\nДата окончания: 2027-01-01\n"
            "Срок, дней: 365\n"
        ),
        "expected": {
            "insured_sum": "100000000",
            "object_value": "125000000",
            "declared_rate": "0.5",
            "declared_premium": "500000",
            "term_days": "365",
            "object_description": "Учебный станок",
            "insured_organization": "ООО Тестовый объект",
            "insurer_organization": "АО Учебное страхование",
            "contract_start": "2026-01-01",
            "contract_end": "2027-01-01",
        },
    },
    "scan": {
        "title": "Учебный договор · изображение",
        "text": (
            "SYNTHETIC DOCUMENT - FICTIONAL DATA ONLY\n\n"
            "Insured organization: LLC Sample Workshop\n"
            "Insurer organization: JSC Demo Insurance\n"
            "Insured object: Training machine\n"
            "Object value: 80 000 000 UZS\n"
            "Insured sum: 60 000 000 UZS\n"
            "Tariff: 1.2%\n"
            "Insurance premium: 720 000 UZS\n"
            "Start date: 2026-04-01\n"
            "End date: 2027-04-01\n"
            "Term in days: 365\n"
        ),
        "expected": {
            "insured_sum": "60000000",
            "object_value": "80000000",
            "declared_rate": "1.2",
            "declared_premium": "720000",
            "term_days": "365",
            "object_description": "Training machine",
            "insured_organization": "LLC Sample Workshop",
            "insurer_organization": "JSC Demo Insurance",
            "contract_start": "2026-04-01",
            "contract_end": "2027-04-01",
        },
    },
    "missing": {
        "title": "Учебный запрос · пропуски",
        "text": (
            "УЧЕБНЫЙ ЗАПРОС — ВСЕ ДАННЫЕ ВЫМЫШЛЕНЫ\n"
            "Страхователь: ООО Тестовый склад\n"
            "Объект страхования: Учебный склад\n"
            "Страховая сумма: 75 000 000 сум\n"
            "Тариф: не указан\nСтраховая премия: не указана\n"
            "Даты и срок не указаны. Стоимость объекта не указана.\n"
        ),
        "expected": {
            **dict.fromkeys(FIELDS),
            "insured_sum": "75000000",
            "object_description": "Учебный склад",
            "insured_organization": "ООО Тестовый склад",
        },
    },
}


def scan_png():
    """Render a fixed sample locally; its transcript is never sent with the image."""
    picture = Image.new("RGB", (1250, 1000), "white")
    draw = ImageDraw.Draw(picture)
    font = ImageFont.load_default(size=28)
    draw.multiline_text((45, 45), SAMPLES["scan"]["text"], fill="black", font=font, spacing=18)
    out = BytesIO()
    picture.save(out, format="PNG")
    return out.getvalue()
