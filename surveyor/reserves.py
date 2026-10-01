"""RNP accounting classification only; no reserve amounts or cancellation refunds."""

SOURCE = "https://lex.uz/docs/1416860"
VERSION = "rnp-groups-1882-2026-10-01"


def classify_rnp(context):
    cls = context.get("insurance_class")
    kind = context.get("reinsurance", "none")
    open_dates = context.get("open_dates", False)
    borrower = context.get("borrower_nonrepayment")
    crop = context.get("crop_insurance")
    group, reason = None, "Укажите класс страхования каждого покрытия"
    if kind == "non_proportional":
        if open_dates:
            reason = (
                "Непропорциональное перестрахование с открытыми датами: требуется уточнить применимую группу"
            )
        else:
            group, reason = 1, "Непропорциональное перестрахование"
    elif open_dates:
        group, reason = 3, "Договор с неопределёнными («открытыми») датами начала и окончания"
    elif cls == 13:
        if borrower is None:
            reason = "Уточните, относится ли класс 13 к ответственности заёмщика за непогашение кредита"
        else:
            group = 2 if borrower else 1
            reason = (
                "Ответственность заёмщика за непогашение кредита"
                if borrower
                else "Общая гражданская ответственность"
            )
    elif cls == 16:
        if crop is None:
            reason = "Уточните, относится ли класс 16 к страхованию урожая сельскохозяйственных культур"
        else:
            group = 4 if crop else 2
            reason = (
                "Страхование урожая сельскохозяйственных культур"
                if crop
                else "Прочие финансовые риски, кроме урожая"
            )
    elif cls in {14, 15}:
        group, reason = 2, "Страхование кредитов или поручительства (гарантий)"
    elif cls in {*range(1, 13), 17}:
        group, reason = 1, "Класс страхования входит в первую учётную группу"
    return {
        "status": "classified" if group else "needs_details",
        "group": group,
        "reason": reason,
        "source_url": SOURCE,
        "rule_version": VERSION,
        "source_paragraph": "10",
        "note": "Классификация для РНП. Сумма резерва, возврат премии и страховой риск здесь не рассчитываются.",
    }
