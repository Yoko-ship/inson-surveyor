import asyncio
import io

import httpx
import pytest
from docx import Document as Word
from PIL import Image
from pypdf import PdfWriter

from surveyor.config import Settings, settings
from surveyor.db import Channel, Indicator, TelegramUpdate
from surveyor.documents import parse_document, read_table
from surveyor.sources import collect_cbu, latest_indicators, store_indicator
from surveyor.telegram import handle_update


def test_docx_text_and_empty_scan():
    doc = Word()
    doc.add_paragraph("Договор\nСтраховая сумма: 500 000\nТариф: 0,5")
    out = io.BytesIO()
    doc.save(out)
    assert parse_document(out.getvalue(), "contract.docx")["fields"]["insured_sum"]["value"] == "500000"
    pdf = PdfWriter()
    pdf.add_blank_page(width=100, height=100)
    out = io.BytesIO()
    pdf.write(out)
    assert parse_document(out.getvalue(), "scan.pdf")["mode"] == "manual"


def test_image_without_ai():
    out = io.BytesIO()
    Image.new("RGB", (20, 20)).save(out, format="PNG")
    result = parse_document(out.getvalue(), "photo.png")
    assert result["mode"] == "manual"
    assert result["fields"] == {}


def test_contract_organizations_dates_and_object():
    text = "Договор\nСтрахователь: ООО «Пример»\nСтраховщик: АО «Страховая компания»\nОбъект страхования: Учебный автомобиль\nДата начала: 01.10.2026\nДата окончания: 30.09.2027"
    fields = parse_document(text.encode(), "contract.txt")["fields"]
    assert fields["insured_organization"]["value"] == "ООО «Пример»"
    assert fields["contract_start"]["value"] == "2026-10-01"
    assert fields["object_description"]["value"] == "Учебный автомобиль"
    personal = parse_document("Страхователь: Иван Иванов".encode(), "person.txt")["fields"][
        "insured_organization"
    ]
    assert personal["value"] is None
    assert "excerpt" not in personal


def test_pdf_page_limit():
    writer = PdfWriter()
    for _ in range(3):
        writer.add_blank_page(width=100, height=100)
    out = io.BytesIO()
    writer.write(out)
    with pytest.raises(ValueError, match="страниц"):
        parse_document(out.getvalue(), "long.pdf", max_pages=2)


def test_excel_table_and_text():
    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    ws.append(["product_code", "year", "claims", "payments"])
    ws.append(["DEMO-FIX", 2025, 3, 1500])
    out = io.BytesIO()
    wb.save(out)
    assert read_table(out.getvalue(), "losses.xlsx")[0]["claims"] == 3
    assert parse_document(out.getvalue(), "losses.xlsx")["mode"] == "rules"


def fake_cbu(monkeypatch, status=200, payload=None):
    class Client:
        def __init__(self, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def get(self, url):
            return httpx.Response(status, json=payload, request=httpx.Request("GET", url))

    monkeypatch.setattr("surveyor.sources.httpx.Client", Client)


@pytest.mark.parametrize("status,payload", [(403, {}), (429, {}), (200, [{"unexpected": "schema"}])])
def test_source_refusal_or_schema_disables_channel(admin, monkeypatch, status, payload):
    fake_cbu(monkeypatch, status, payload)
    with admin.factory() as db:
        result = collect_cbu(db, force=True)
        assert result["status"] == "error"
        channel = db.get(Channel, "cbu")
        assert not channel.enabled
        assert channel.error


def test_source_version_history_cache_and_staleness(admin, monkeypatch):
    fake_cbu(monkeypatch, 200, [{"Ccy": "USD", "Rate": "12000", "Nominal": "1", "Date": "01.01.2020"}])
    with admin.factory() as db:
        result = collect_cbu(db, force=True)
        assert result["status"] == "collected"
        assert latest_indicators(db)[0]["stale"]
        row = db.query(Indicator).first()
        data = {**row.data, "value": "13000"}
        store_indicator(db, "cbu", data)
        db.commit()
        assert db.query(Indicator).count() == 2
        assert latest_indicators(db)[0]["value"] == "13000"
        assert collect_cbu(db)["status"] == "cached"


def test_telegram_deduplication_and_private_only(admin, monkeypatch):
    sent = []

    async def fake_send(method, **kwargs):
        sent.append((method, kwargs))
        return {}

    monkeypatch.setattr("surveyor.telegram.call_telegram", fake_send)
    update = {"update_id": 50, "message": {"chat": {"id": 123456, "type": "private"}, "text": "/id"}}
    with admin.factory() as db:
        asyncio.run(handle_update(update, db))
        asyncio.run(handle_update(update, db))
        assert len(sent) == 1
        assert db.get(TelegramUpdate, 50)
        update["update_id"] = 51
        update["message"]["chat"]["type"] = "group"
        asyncio.run(handle_update(update, db))
        assert len(sent) == 1


def test_webhook_secret(admin, monkeypatch):
    monkeypatch.setattr(settings, "telegram_webhook_secret", "webhook-test")
    assert admin.post("/telegram/webhook", json={"update_id": 1}).status_code == 403
    assert (
        admin.post(
            "/telegram/webhook",
            json={"update_id": 1},
            headers={"X-Telegram-Bot-Api-Secret-Token": "webhook-test"},
        ).status_code
        == 200
    )


def test_real_data_guard():
    with pytest.raises(ValueError, match="Uzbekistan"):
        Settings(_env_file=None, data_mode="real", hosting_country="US")
