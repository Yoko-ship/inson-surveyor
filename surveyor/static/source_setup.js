"use strict";

function sourceCoveragePanel(data) {
  const metricList = (items) =>
    items.length ? items.map(esc).join(", ") : "—";
  return `<section class="panel" id="source-coverage"><h3>Связь статистики с тарифом</h3><p class="form-hint">Загруженные данные влияют на тариф через правила класса. Базовые значения и чувствительность задаёт страховщик, затем утверждает актуарий.</p>${data.templates.map((row) => `<div class="file-card"><h4>${esc(row.name)}</h4><p><strong>Связанные показатели:</strong> <span data-no-translate>${metricList(row.linked_metrics)}</span></p><p><strong>В правилах есть, актуальных данных нет:</strong> <span data-no-translate>${metricList(row.missing_metrics)}</span></p><p><strong>Данные есть, правила не настроены:</strong> <span data-no-translate>${metricList(row.unmapped_metrics)}</span></p><p><strong>Рыночная котировка:</strong> <span>${row.market_available ? "Доступна для класса" : "Нужна котировка с источником и датой"}</span></p><p class="form-hint">Наличие данных по классу не гарантирует данные для каждого региона и вида объекта.</p></div>`).join("")}</section>`;
}

function marketQuoteForm() {
  const classes = [...new Set(state.products.map((p) => p.class_code))];
  return `<section class="panel"><h3>Рыночная страховая котировка</h3><p class="form-hint">Внесите проверенное предложение с сопоставимым покрытием. Фиксированная ставка пересчитывается в годовую по сроку. Отношение премий NAPP к обязательствам не является годовой котировкой.</p><form id="market-quote-form"><div class="form-grid">${select(
    "class_code",
    "Класс",
    classes.map((c) => [c, c]),
    classes[0],
  )}${select(
    "object_type",
    "Вид объекта",
    [
      ["vehicle", "Автомобиль"],
      ["equipment", "Оборудование"],
      ["housing", "Жильё / техника"],
      ["large", "Крупный объект"],
      ["other", "Другое"],
    ],
    "vehicle",
  )}${select(
    "region",
    "Регион",
    state.regions.map((r) => [r.code, r[state.locale]]),
    "all",
  )}${field("rate", "Исходная ставка котировки, %", "", "number", 'required min="0.00000001" max="100" step="any"')}${select(
    "basis",
    "Тип ставки котировки",
    [
      ["annual", "Годовая"],
      ["fixed", "Фиксированная"],
    ],
    "annual",
  )}${field("term_days", "Срок котировки, дней", 365, "number", 'required min="1" max="36500"')}${field("source_url", "Ссылка на источник", "", "url", "required")}${field("observation_date", "Дата котировки", today(), "date", `required max="${today()}"`)}${field("stale_days", "Срок актуальности, дней", 180, "number", 'required min="1" max="3650"')}</div><label>Сопоставимые условия страхования<textarea name="coverage" required minlength="5" maxlength="1000"></textarea></label><p><strong>Годовой эквивалент котировки:</strong> <span id="market-quote-annual">—</span></p><button type="submit" class="primary">Сохранить котировку</button><p class="form-error"></p></form></section>`;
}

function bindMarketQuote() {
  const form = $("#market-quote-form");
  const update = () => {
    const rate = Number(form.elements.rate.value);
    const days = Number(form.elements.term_days.value);
    const annual =
      form.elements.basis.value === "fixed" ? (rate * 365) / days : rate;
    $("#market-quote-annual").textContent =
      rate > 0 && days > 0 && Number.isFinite(annual)
        ? new Intl.NumberFormat(state.locale, {
            maximumFractionDigits: 8,
          }).format(annual) + "%"
        : "—";
  };
  for (const key of ["rate", "basis", "term_days"])
    form.elements[key].oninput = update;
  bindForm("#market-quote-form", async (data) => {
    data.term_days = Number(data.term_days);
    data.stale_days = Number(data.stale_days);
    await post("/admin/market-quotes", data);
    toast("Рыночная котировка сохранена");
    await adminIndicators();
  });
}

function sourceMetricName(metric) {
  const labels = {
    registered_thefts: "Зарегистрированные кражи",
    registered_robberies: "Грабежи и разбои",
    mortality_per_mille: "Смертность на 1000 населения",
    population_thousands: "Население на начало года, тыс. человек",
    napp_ref_company_premiums: "Премии компании",
    napp_ref_company_payments: "Выплаты компании",
    napp_ref_claims_received: "Претензии полученные",
    napp_ref_claims_paid: "Претензии оплаченные",
    napp_ref_claims_refused: "Претензии отклонённые",
    napp_ref_claims_unsettled: "Претензии неурегулированные",
    napp_ref_bundle_premiums: "Премии по набору классов",
    napp_ref_bundle_payments: "Выплаты по набору классов",
    napp_ref_bundle_liabilities: "Обязательства по набору классов",
    napp_ref_regional_premiums: "Региональные премии рынка",
    napp_ref_regional_payments: "Региональные выплаты рынка",
    napp_ref_inson_premiums_market_share: "Доля INSON в премиях всего рынка",
    napp_ref_inson_payments_market_share: "Доля INSON в выплатах всего рынка",
    napp_ref_inson_subdivision_premiums: "Премии подразделений INSON",
    napp_ref_inson_subdivision_payments: "Выплаты подразделений INSON",
    napp_ref_inson_payment_premium_ratio: "INSON: выплаты / премии",
    napp_ref_inson_region_to_company_ratio:
      "INSON: отношение региона к компании",
  };
  return window.SurveyorI18n.text(labels[metric] || metric);
}
