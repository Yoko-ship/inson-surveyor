"""Expose missing statistical mappings without inventing insurer policy."""

from sqlalchemy import select

from surveyor.db import ClassTemplate
from surveyor.sources import latest_indicators


def source_coverage(db):
    observations = latest_indicators(db)
    metrics = {}
    for item in observations:
        key = (item["metric"], item.get("class_code", "all"), item.get("object_type", "all"), item["unit"])
        entry = metrics.setdefault(
            key,
            {
                "metric": key[0],
                "class_code": key[1],
                "object_type": key[2],
                "unit": key[3],
                "reference_only": bool(item.get("reference_only") or item["metric"].startswith("napp_ref_")),
                "fresh": 0,
                "stale": 0,
            },
        )
        entry["stale" if item["stale"] else "fresh"] += 1
    templates, seen = [], set()
    for row in db.scalars(select(ClassTemplate).order_by(ClassTemplate.created_at.desc())):
        if row.class_code in seen:
            continue
        seen.add(row.class_code)
        relevant = [
            i
            for i in observations
            if not i["stale"]
            and i.get("class_code", "all") in {"all", row.class_code}
            and not i["metric"].startswith(("fx_", "napp_ref_"))
            and not i.get("reference_only")
        ]
        available = {i["metric"] for i in relevant if i.get("annual_market_rate") is None}
        configured = set(row.data.get("indicator_metrics", [])) | set(row.data.get("indicator_rules", {}))
        templates.append(
            {
                "class_code": row.class_code,
                "name": row.data.get("name", row.class_code),
                "approved": bool(row.approved_by),
                "linked_metrics": sorted(configured & available),
                "missing_metrics": sorted(configured - available),
                "unmapped_metrics": sorted(available - configured),
                "market_available": any(
                    i.get("annual_market_rate") is not None and i.get("class_code") == row.class_code
                    for i in relevant
                ),
            }
        )
    return {
        "metrics": sorted(metrics.values(), key=lambda m: (m["metric"], m["class_code"], m["object_type"])),
        "templates": templates,
    }
