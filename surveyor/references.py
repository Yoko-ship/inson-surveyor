"""Versioned public legal/weather/market material, separate from numeric adjustments."""

import hashlib
import json
from datetime import date
from html.parser import HTMLParser

from sqlalchemy import select

from surveyor.db import PublicReference, audit
from surveyor.schemas import ReferenceInput


class PageText(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts, self.skip = [], 0

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style", "noscript"}:
            self.skip += 1

    def handle_endtag(self, tag):
        if tag in {"script", "style", "noscript"}:
            self.skip = max(0, self.skip - 1)

    def handle_data(self, data):
        if not self.skip and data.strip():
            self.parts.append(data.strip())


def public_text(content):
    parser = PageText()
    parser.feed(content.decode("utf-8-sig"))
    text = "\n".join(parser.parts)
    if not text or len(text) > 50000:
        raise ValueError("Public document text must contain 1–50,000 characters")
    return text


def store_reference(db, channel, data, actor=None):
    data = ReferenceInput.model_validate(data).model_dump(mode="json")
    sha = hashlib.sha256(json.dumps(data, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    previous = db.scalar(
        select(PublicReference)
        .where(PublicReference.channel_code == channel, PublicReference.source_url == data["source_url"])
        .order_by(PublicReference.fetched_at.desc())
        .limit(1)
    )
    if previous and previous.sha256 == sha:
        return previous
    row = PublicReference(channel_code=channel, source_url=data["source_url"], sha256=sha, data=data)
    db.add(row)
    db.flush()
    audit(
        db,
        actor,
        "reference.changed" if previous else "reference.created",
        row.id,
        {"previous_id": previous.id if previous else None, "channel": channel, "title": data["title"]},
    )
    return row


def reference_view(row):
    d = row.data
    observed = d.get("observation_date")
    return {
        **d,
        "id": row.id,
        "channel": row.channel_code,
        "sha256": row.sha256,
        "fetched_at": row.fetched_at.isoformat(),
        "stale": observed is None or (date.today() - date.fromisoformat(observed)).days > d["stale_days"],
    }


def latest_references(db):
    rows = db.scalars(select(PublicReference).order_by(PublicReference.fetched_at.desc())).all()
    seen, result = set(), []
    for row in rows:
        key = (row.channel_code, row.source_url)
        if key not in seen:
            result.append(reference_view(row))
            seen.add(key)
    return result
