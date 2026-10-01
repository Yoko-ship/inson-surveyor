"""Bounded public-file adapters. Never interpolate inspection/customer data into requests."""

import calendar
import ipaddress
import json
import re
import socket
import time
from datetime import date
from decimal import Decimal
from html.parser import HTMLParser
from urllib.parse import urlsplit
from urllib.robotparser import RobotFileParser

import httpx
from pydantic import Field, HttpUrl, model_validator

from surveyor.documents import read_table
from surveyor.regions import region_code
from surveyor.schemas import IndicatorInput, Strict
from surveyor.source_lock import host_lock

AGENT = "Surveyor/0.2 (+public insurance statistics; no customer queries)"
HOSTS = {
    "stat": {"api.siat.stat.uz", "siat.stat.uz", "stat.uz"},
    "egov": {"data.egov.uz", "olddata.gov.uz"},
    "napp": {"napp.uz"},
    "lex": {"lex.uz"},
    "avtoelon": {"avtoelon.uz"},
    "seismos": {"seismos.uz"},
    "weather": {"hydromet.uz", "meteo.uz", "monitoring.meteo.uz"},
    "auction": {"e-auksion.uz"},
    "exchange": {"uzex.uz"},
    "construction": {"mc.uz"},
    "new_cars": {"uzavtosanoat.uz"},
    "customs": {"customs.uz"},
    "licenses": {"license.gov.uz"},
    "court": {"public.sud.uz"},
}
FORMATS = {"json", "csv", "xlsx", "html_table", "siat", "document", "napp"}


class SourceConfig(Strict):
    url: HttpUrl
    format: str
    permission_url: HttpUrl
    permission_note: str = Field(min_length=15, max_length=2000)
    reference: dict = Field(default_factory=dict, max_length=10)
    columns: dict[str, str] = Field(default_factory=dict, max_length=20)
    constants: dict = Field(default_factory=dict, max_length=20)
    json_path: str = Field(default="", max_length=200)
    table_index: int = Field(default=0, ge=0, le=30)
    interval_hours: int = Field(default=24, ge=24, le=720)

    @model_validator(mode="after")
    def valid_mapping(self):
        if self.format not in FORMATS:
            raise ValueError("Допустимые форматы: JSON, CSV, XLSX, HTML table, SIAT")
        allowed = set(IndicatorInput.model_fields)
        if (set(self.columns) | set(self.constants)) - allowed:
            raise ValueError("Неизвестное поле показателя")
        # Data files cannot approve their own adjustments.
        if self.format == "document":
            from surveyor.schemas import ReferenceInput

            ReferenceInput.model_validate(
                {**self.reference, "source_url": str(self.url), "text": "preflight"}
            )
        elif self.format not in {"siat", "napp"}:
            needed = {"metric", "period", "value", "unit", "observation_date"}
            if needed - (set(self.columns) | set(self.constants)):
                raise ValueError("Укажите соответствие полей: metric, period, value, unit, observation_date")
        return self


def checked_url(url, channel, resolve=True):
    p = urlsplit(str(url))
    host = (p.hostname or "").lower()
    allowed = HOSTS.get(channel, set())
    if (
        p.scheme != "https"
        or p.username
        or p.password
        or p.port not in (None, 443)
        or p.fragment
        or host.removeprefix("www.") not in allowed
    ):
        raise ValueError(
            "Разрешён только HTTPS официального домена этого канала без пароля и перенаправлений"
        )
    if resolve:
        addresses = socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
        if not addresses or any(not ipaddress.ip_address(a[4][0]).is_global for a in addresses):
            raise ValueError("Адрес источника не является публичным")
    return str(url)


class AccessRefused(ValueError):
    pass


class FormatChanged(ValueError):
    pass


def fetch_public(config, channel):
    url = checked_url(config["url"], channel)
    p = urlsplit(url)
    robots_url = f"https://{p.netloc}/robots.txt"
    with (
        host_lock(p.hostname),
        httpx.Client(
            timeout=25,
            follow_redirects=False,
            headers={"User-Agent": AGENT, "Accept": "application/json,text/csv,text/html,*/*"},
        ) as client,
    ):
        robots = client.get(robots_url)
        if robots.status_code in {401, 403, 429}:
            raise AccessRefused("Отказ при проверке robots.txt; канал отключён")
        delay = 1.0
        if robots.status_code == 200:
            # Some sites redirect robots.txt to an HTML home page: do not treat that as permission.
            if "<html" in robots.text[:1000].lower():
                raise AccessRefused("robots.txt вернул HTML; требуется повторная проверка доступа")
            # Merge repeated wildcard groups conservatively (stdlib takes only the first).
            text = robots.text.lstrip("\ufeff")
            groups = re.split(r"(?im)(?=^user-agent:)", text)
            relevant = [g for g in groups if re.match(r"(?i)user-agent:\s*(?:\*|surveyor)\s*(?:\n|$)", g)]
            for group in relevant or [text]:
                rp = RobotFileParser()
                rp.parse(group.splitlines())
                if not rp.can_fetch("Surveyor", url):
                    raise AccessRefused("robots.txt запрещает этот адрес; используйте загрузку файла")
                delay = max(delay, rp.crawl_delay("Surveyor") or 1)
            if delay > 60:
                raise AccessRefused("Источник требует интервал свыше 60 секунд; используйте файл")
        elif robots.status_code != 404:
            raise AccessRefused("Не удалось проверить robots.txt; канал отключён до проверки")
        time.sleep(delay)
        with client.stream("GET", url) as response:
            if response.status_code in {401, 403, 429}:
                raise AccessRefused("Источник отказал в доступе; автоматические повторы отключены")
            if response.is_redirect:
                raise FormatChanged("Источник перенаправляет запрос: проверьте и задайте конечный адрес")
            response.raise_for_status()
            chunks, size = [], 0
            for chunk in response.iter_bytes():
                size += len(chunk)
                if size > 15 * 1024 * 1024:
                    raise FormatChanged("Файл источника превышает 15 МБ")
                chunks.append(chunk)
            return b"".join(chunks)


class Tables(HTMLParser):
    def __init__(self):
        super().__init__()
        self.tables, self.rows, self.row, self.cell = [], None, None, None

    def handle_starttag(self, tag, attrs):
        if tag == "table":
            self.rows = []
        elif tag == "tr" and self.rows is not None:
            self.row = []
        elif tag in {"td", "th"} and self.row is not None:
            if any(k in {"rowspan", "colspan"} and v != "1" for k, v in attrs):
                raise FormatChanged("Объединённые ячейки: загрузите нормализованный файл")
            self.cell = ""

    def handle_data(self, data):
        if self.cell is not None:
            self.cell += data

    def handle_endtag(self, tag):
        if tag in {"td", "th"} and self.cell is not None:
            self.row.append(self.cell.strip())
            self.cell = None
        elif tag == "tr" and self.row is not None:
            if self.row:
                self.rows.append(self.row)
            self.row = None
        elif tag == "table" and self.rows is not None:
            self.tables.append(self.rows)
            self.rows = None


def parse_siat(payload, config):
    if not isinstance(payload, list) or len(payload) != 1 or not {"metadata", "data"} <= payload[0].keys():
        raise FormatChanged("Изменилась оболочка SIAT")
    rows = payload[0]["data"]
    metadata = {r["name_en"]: r.get("value_en") for r in payload[0]["metadata"]}
    unit = metadata.get("Unit of measurement")
    if not rows or not unit:
        raise FormatChanged("SIAT: отсутствуют данные или единица")
    result = []
    for row in rows:
        if set(row) != set(rows[0]):
            raise FormatChanged("SIAT: столбцы строк не совпадают")
        if "Code" not in row or "Klassifikator_ru" not in row:
            raise FormatChanged("SIAT: отсутствует классификатор")
        periods = [k for k in row if re.fullmatch(r"20\d{2}(?:-Q[1-4]|-M(?:0[1-9]|1[0-2]))?", k)]
        if not periods:
            raise FormatChanged("SIAT: ожидаются столбцы YYYY, YYYY-Qn или YYYY-Mnn")
        for period in periods:
            if row[period] in (None, "", "-"):
                continue
            year = int(period[:4])
            month = int(period[-1]) * 3 if "-Q" in period else int(period[-2:]) if "-M" in period else 12
            end = date(year, month, calendar.monthrange(year, month)[1])
            if end > date.today():
                continue
            result.append(
                IndicatorInput(
                    **{
                        **config.get("constants", {}),
                        "period": period,
                        "value": row[period],
                        "unit": unit,
                        "region": region_code(str(row["Code"])),
                        "source_url": config["url"],
                        "observation_date": end,
                    }
                )
            )
    return result, sorted(rows[0].keys())


def parse_public(data, config):
    fmt = config["format"]
    if fmt in {"json", "siat"}:
        rows = json.loads(data, parse_float=Decimal)
        if fmt == "siat":
            return parse_siat(rows, config)
        for key in filter(None, config.get("json_path", "").split(".")):
            rows = rows[key]
    elif fmt in {"csv", "xlsx"}:
        rows = read_table(data, "source." + fmt)
    else:
        parser = Tables()
        parser.feed(data.decode("utf-8-sig"))
        table = parser.tables[config.get("table_index", 0)]
        headers = table[0]
        if len(set(headers)) != len(headers):
            raise FormatChanged("Повторяющиеся столбцы")
        rows = [dict(zip(headers, r, strict=True)) for r in table[1:]]
    if (
        not isinstance(rows, list)
        or not rows
        or len(rows) > 10000
        or not all(isinstance(r, dict) for r in rows)
    ):
        raise FormatChanged("Ожидается таблица от 1 до 10 000 строк")
    schema = sorted(rows[0])
    items = []
    for row in rows:
        if sorted(row) != schema:
            raise FormatChanged("Разные столбцы в строках файла")
        item = {**config.get("constants", {}), **{k: row[v] for k, v in config["columns"].items()}}
        item.setdefault("source_url", config["url"])
        item["region"] = region_code(item.get("region", "all"))
        items.append(IndicatorInput.model_validate(item))
    return items, schema


SIAT_DATASETS = [
    ("stat_crime", 800, "registered_crimes", "Зарегистрированные преступления", "all"),
    ("stat_housing", 1244, "housing_area", "Площадь жилищного фонда", "housing"),
    ("stat_accidents", 3251, "road_accidents", "ДТП: опубликованные квартальные периоды", "vehicle"),
    ("stat_prices", 4690, "consumer_price_index", "Индекс потребительских цен: к предыдущему месяцу", "all"),
]


def seed_public_channels(db):
    from surveyor.db import Channel

    for code, dataset, metric, title, object_type in SIAT_DATASETS:
        if db.get(Channel, code):
            continue
        db.add(
            Channel(
                code=code,
                enabled=True,
                data={
                    "domain": "siat.stat.uz",
                    "access": "official_file",
                    "note": title,
                    "host_channel": "stat",
                    "reviewed_on": "2026-10-01",
                    "review_status": "connect",
                    "config": SourceConfig(
                        url=f"https://api.siat.stat.uz/media/uploads/sdmx/sdmx_data_{dataset}.json",
                        format="siat",
                        permission_url=f"https://siat.stat.uz/data/{dataset}/?lang=ru",
                        permission_note="Official downloadable JSON, CC BY 4.0 attribution, robots.txt permits access (2026-10-01).",
                        constants={
                            "metric": metric,
                            "object_type": object_type,
                            "stale_days": 550 if dataset in {800, 1244} else 200 if dataset == 3251 else 90,
                        },
                    ).model_dump(mode="json"),
                },
            )
        )


def seed_napp(db):
    from surveyor.db import Channel
    from surveyor.napp import NAPP_INDEX

    if not db.get(Channel, "napp_market"):
        db.add(
            Channel(
                code="napp_market",
                enabled=True,
                data={
                    "domain": "napp.uz",
                    "host_channel": "napp",
                    "access": "official_file",
                    "note": "Статистика страхового рынка по классам: премии, выплаты, обязательства, убыточность",
                    "review_status": "connect",
                    "reviewed_on": "2026-10-01",
                    "config": SourceConfig(
                        url=NAPP_INDEX,
                        format="napp",
                        permission_url=NAPP_INDEX,
                        permission_note="Official published XLSX downloads; robots.txt allows access; source attribution retained.",
                    ).model_dump(mode="json"),
                },
            )
        )


def seed_access_review(db):
    from surveyor.db import Channel

    reviews = {
        "avtoelon": (
            "contract_required",
            "Автоматический доступ требует письменного разрешения; п. 5.3 соглашения",
            "https://avtoelon.uz/content/articles/agreement/",
        ),
        "weather": (
            "contract_required",
            "Meteo API: требуется заявка и предоставленный доступ; пока загрузка файла",
            "https://data.meteo.uz/",
        ),
        "seismos": (
            "manual",
            "Сайт на технических работах; подтверждённый поток событий недоступен",
            "https://seismos.uz/",
        ),
        "exchange": (
            "manual_only",
            "robots.txt запрещает /page, включая страницы котировок; загрузка файла",
            "https://uzex.uz/robots.txt",
        ),
        "napp": (
            "official_file",
            "Подключён отдельный канал napp_market: официальные XLSX по классам",
            "https://napp.uz/en/pages/statistics-and-analysis-for-im",
        ),
        "stat": (
            "official_file",
            "Подключены четыре канала SIAT: преступность, ДТП, жильё, цены",
            "https://siat.stat.uz/data/?lang=ru",
        ),
    }
    for code, (access, note, evidence) in reviews.items():
        row = db.get(Channel, code)
        if row and not row.data.get("config") and row.data.get("reviewed_on") != "2026-10-01":
            row.data = {
                **row.data,
                "access": access,
                "note": note,
                "review_evidence": evidence,
                "reviewed_on": "2026-10-01",
            }
