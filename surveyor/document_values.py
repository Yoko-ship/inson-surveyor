"""Conservative document values: ambiguous numbers stay available for human review."""

import re
from datetime import date
from decimal import Decimal


def document_number(raw, field):
    match = re.match(r"[0-9][0-9 .,\u00a0\u202f]*", raw)
    if not match:
        return None
    token = match.group().strip()
    suffix = raw[match.end() :].strip()
    units = (
        r"(?:%|процент\w*\b|годовых\b|annual\b)"
        if field == "declared_rate"
        else r"(?:день|дня|дней|days?|kun)\b"
        if field == "term_days"
        else r"(?:UZS|сум|сўм|so['‘’]?m)\b"
    )
    # Unknown scales, ranges and foreign money must not become bare UZS values.
    if suffix and not re.match(units, suffix, re.I):
        return None
    token = token.replace("\u00a0", " ").replace("\u202f", " ")
    if " " in token:
        if not re.fullmatch(r"[0-9]{1,3}(?: [0-9]{3})+(?:[.,][0-9]+)?", token):
            return None
        token = token.replace(" ", "")
    separators = {c for c in token if c in ",."}
    if len(separators) == 2:
        decimal = "," if token.rfind(",") > token.rfind(".") else "."
        group = "." if decimal == "," else ","
        if not re.fullmatch(
            r"[0-9]{1,3}(?:" + re.escape(group) + r"[0-9]{3})+" + re.escape(decimal) + r"[0-9]+", token
        ):
            return None
        token = token.replace(group, "").replace(decimal, ".")
    elif separators:
        sep = next(iter(separators))
        parts = token.split(sep)
        if len(parts) > 2:
            if field == "declared_rate" or not (
                1 <= len(parts[0]) <= 3 and all(len(p) == 3 for p in parts[1:])
            ):
                return None
            token = "".join(parts)
        else:
            if not parts[1]:
                return None
            # A lone separator followed by three digits could mean either 100.000 or 100,000.
            if len(parts[1]) == 3 and parts[0] != "0" and field != "declared_rate":
                return None
            token = token.replace(sep, ".")
    number = Decimal(token)
    if number > Decimal("1e18") or (field == "declared_rate" and number > 100):
        return None
    if field == "term_days" and (number != number.to_integral_value() or not 1 <= number <= 36500):
        return None
    return format(number, "f")


def derive_document_term(fields, filename):
    """Use the date difference only when no explicit duration was supplied."""
    start, end = (fields.get(k, {}).get("value") for k in ("contract_start", "contract_end"))
    current = fields.get("term_days", {})
    if current.get("value") is not None and current.get("derived_from") != "contract_dates":
        return
    if not start or not end:
        if current.get("derived_from") == "contract_dates":
            fields["term_days"] = {"value": None, "status": "unavailable", "source": filename}
        return
    days = (date.fromisoformat(end) - date.fromisoformat(start)).days
    fields["term_days"] = {
        **current,
        "value": str(days) if 1 <= days <= 36500 else None,
        "status": "extracted" if 1 <= days <= 36500 else "needs_review",
        "source": filename,
        "derived_from": "contract_dates",
        "excerpt": f"{start} → {end}; срок по разнице дат, дата окончания не включена. Проверьте условия договора.",
    }
    if current.get("derived_from") and current.get("value") != fields["term_days"]["value"]:
        fields["term_days"]["original"] = current.get("original", current.get("value"))
