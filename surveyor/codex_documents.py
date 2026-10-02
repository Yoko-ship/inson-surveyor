"""Bounded document previews through the owner's existing Codex sign-in."""

import io
import re
import tempfile
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path

import pypdfium2 as pdfium
from PIL import Image, ImageOps

from surveyor import ai_config, ai_providers
from surveyor.document_values import document_number
from surveyor.documents import extract_text
from surveyor.pilot_samples import FIELDS


def prepare(data, filename, directory, limits=None):
    """Render all PDF pages, including mixed text/scans. Never silently truncate."""
    limits = limits or ai_config.load().limits
    text, _ = extract_text(data, filename, limits.max_pages)
    if len(text) > limits.max_text_chars:
        raise ValueError(f"Лимит текста: {limits.max_text_chars:,} символов.".replace(",", " "))
    suffix = Path(filename).suffix.lower()
    images = []

    def save_image(im):
        im = ImageOps.exif_transpose(im).convert("RGB")
        im.thumbnail((2000, 2000))
        path = directory / f"page-{len(images) + 1}.png"
        im.save(path, "PNG")
        images.append(path)

    if suffix == ".pdf":
        with pdfium.PdfDocument(data) as pdf:
            if not 1 <= len(pdf) <= limits.max_pages:
                raise ValueError(f"Допустимо от 1 до {limits.max_pages} страниц PDF.")
            for index in range(len(pdf)):
                page = pdf[index]
                try:
                    width, height = page.get_size()
                    bitmap = page.render(scale=min(2, 2000 / max(width, height)))
                    try:
                        save_image(bitmap.to_pil())
                    finally:
                        bitmap.close()
                finally:
                    page.close()
    elif suffix in {".jpg", ".jpeg", ".png", ".webp"}:
        with Image.open(io.BytesIO(data)) as im:
            save_image(im)
    if not text.strip() and not images:
        raise ValueError("Документ пуст: нет текста или страниц для распознавания.")
    return text, images


def assess(readings, text, has_images):
    rows = []
    for name in FIELDS:
        value, quote = readings[name]["value"], readings[name]["quote"]
        valid = value is None and not quote
        if value is not None:
            valid = bool(value.strip() and quote.strip())
            if name in FIELDS[:5]:
                try:
                    amount = Decimal(value)
                    valid &= amount.is_finite() and 0 <= amount <= Decimal("1e18")
                    if name == "declared_rate":
                        valid &= amount <= 100
                    if name == "term_days":
                        valid &= 1 <= amount <= 36500 and amount == amount.to_integral_value()
                    candidates = re.findall(r"[0-9][0-9 .,\u00a0\u202f]*", quote)
                    supported = [document_number(candidate.rstrip(" .,"), name) for candidate in candidates]
                    valid &= any(x is not None and Decimal(x) == amount for x in supported)
                    if name in {"insured_sum", "object_value", "declared_premium"}:
                        valid &= not bool(re.search(r"\b(?:USD|EUR|доллар\w*|евро)\b|\$", quote, re.I))
                except InvalidOperation:
                    valid = False
            elif name.startswith("contract_"):
                try:
                    parsed_date = date.fromisoformat(value)
                    valid &= parsed_date.isoformat() == value
                    valid &= any(
                        parsed_date.strftime(fmt) in quote for fmt in ("%Y-%m-%d", "%d.%m.%Y", "%d/%m/%Y")
                    )
                except ValueError:
                    valid = False
            elif name.endswith("organization"):
                valid &= bool(re.search(r"\b(?:ООО|АО|ОАО|ЗАО|МЧЖ|АЖ|MChJ|AJ|LLC|JSC)\b", value, re.I))
                valid &= value in quote
            elif name == "object_description":
                valid &= value in quote
        quote_found = bool(quote.strip() and quote in text)
        if value is not None and not has_images and not quote_found:
            valid = False
        rows.append(
            {
                "field": name,
                "value": value if valid else None,
                "quote": quote if valid else "",
                "status": "needs_review" if valid else "rejected",
                # A verbatim text match does not establish that the value is correct.
                "quote_found_in_text": quote_found,
            }
        )
    return rows


def recognize_document(data, filename, locale="ru", config=None):
    config = config or ai_config.load()
    with tempfile.TemporaryDirectory(prefix="surveyor-document-") as folder:
        directory = Path(folder)
        try:
            text, images = prepare(data, filename, directory, config.limits)
        except ValueError:
            raise
        except Exception:
            raise ValueError("Не удалось прочитать документ. Проверьте формат и содержимое.") from None
        result = ai_providers.generate(config, text, images, directory, locale=locale)
    return {
        "fields": assess(result["fields"], text, bool(images)),
        "summary": result["summary"],
        "display_mode": config.display_mode,
        "config_revision": ai_config.digest(config),
        "provider": config.provider,
        "saved": False,
    }
