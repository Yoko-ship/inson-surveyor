"use strict";

window.SurveyorPolicy = (() => {
  let source;
  const kinds = {
    minimum: "Числовой минимум",
    variants: "Варианты тарифа",
    components: "Составной продукт",
    program: "Нужна программа",
    head_office: "Согласование с ЦО",
    master_agreement: "Нужен основной договор",
    normative: "Нужен нормативный акт",
    unspecified: "Строка не заполнена",
    clarification: "Нужно уточнение",
  };
  async function prepare() {
    source = await api("/policy/catalog");
    return source;
  }
  const entry = (code) => source?.entries.find((r) => r.code === code);
  function rnpFields(d = {}) {
    return `<div class="form-grid">${select("rnp_class", "Класс страхования покрытия", [["", "Не указан"], ...Array.from({ length: 17 }, (_, i) => [String(i + 1), String(i + 1)])], String(d.insurance_class || ""))}${select(
      "rnp_reinsurance",
      "Перестрахование",
      [
        ["none", "Не применяется"],
        ["proportional", "Пропорциональное"],
        ["non_proportional", "Непропорциональное"],
      ],
      d.reinsurance || "none",
    )}${select(
      "rnp_borrower",
      "Класс 13: ответственность заёмщика за непогашение",
      [
        ["", "Не уточнено"],
        ["true", "Да"],
        ["false", "Нет"],
      ],
      d.borrower_nonrepayment == null ? "" : String(d.borrower_nonrepayment),
    )}${select(
      "rnp_crop",
      "Класс 16: страхование урожая",
      [
        ["", "Не уточнено"],
        ["true", "Да"],
        ["false", "Нет"],
      ],
      d.crop_insurance == null ? "" : String(d.crop_insurance),
    )}</div><label class="check"><input name="rnp_open" type="checkbox" ${d.open_dates ? "checked" : ""}>Открытые даты начала и окончания договора</label><p class="form-hint">Для составного договора каждое покрытие классифицируется отдельно. Учётная группа не изменяет страховой балл или тариф.</p>`;
  }
  function readRnp(values) {
    if (
      !values.rnp_class &&
      values.rnp_reinsurance !== "non_proportional" &&
      !values.rnp_open
    )
      return null;
    const d = {
      insurance_class: values.rnp_class ? Number(values.rnp_class) : null,
      reinsurance: values.rnp_reinsurance || "none",
      open_dates: Boolean(values.rnp_open),
    };
    if (d.insurance_class === 13 && values.rnp_borrower !== "")
      d.borrower_nonrepayment = values.rnp_borrower === "true";
    if (d.insurance_class === 16 && values.rnp_crop !== "")
      d.crop_insurance = values.rnp_crop === "true";
    return d;
  }
  async function page() {
    await prepare();
    $("#content").innerHTML =
      heading(
        "Тарифная политика и РНП",
        "Данные из предоставленного документа INSON.",
      ) +
      `<section class="panel"><div class="panel-head"><h3>${esc(source.title)}</h3>${source.source_available ? '<a class="secondary" href="/api/policy/source" target="_blank" rel="noopener">Открыть исходный PDF</a>' : ""}</div><p><span>Дата документа</span>: ${esc(source.document_date)} · <span>Строк в каталоге</span>: ${source.entries.length}</p><div class="notice">Это справочник минимумов. Актуальность, дата начала действия и база расчёта подтверждаются при настройке версии тарифа.</div><p class="form-hint" data-no-translate>${esc(source.period_note)}</p><div class="form-grid">${field("policy_search", "Поиск по коду или названию")}${select("policy_kind", "Условия тарифа", [["", "Все"], ...Object.entries(kinds)])}</div><p id="catalog-count" aria-live="polite"></p><div class="table-wrap"><table><thead><tr><th>КОД / ПРОДУКТ</th><th>МИНИМУМ / УСЛОВИЯ</th><th>КОМИССИЯ</th><th>СТРАНИЦА</th><th></th></tr></thead><tbody id="catalog-rows"></tbody></table></div></section><section class="panel"><h3>Учётная группа РНП</h3><p class="form-hint">Определение группы по пункту 10. Сумма резерва и возврат премии здесь не рассчитываются.</p><form id="rnp-form">${rnpFields()}<button class="secondary" type="submit">Определить группу</button></form><div id="rnp-result" aria-live="polite"></div><a href="https://lex.uz/docs/1416860" target="_blank" rel="noopener">Положение о страховых резервах</a></section>`;
    await window.SurveyorFactors.mount($("#content"));
    const render = () => {
      const q = $("[name=policy_search]").value.trim().toLocaleLowerCase();
      const kind = $("[name=policy_kind]").value;
      const rows = source.entries.filter(
        (r) =>
          (!kind || r.kind === kind) &&
          `${r.code} ${r.name}`.toLocaleLowerCase().includes(q),
      );
      $("#catalog-count").textContent =
        `${rows.length} / ${source.entries.length}`;
      $("#catalog-rows").innerHTML =
        rows
          .map(
            (r) =>
              `<tr><td data-no-translate><strong>${esc(r.code)}</strong><small>${esc(r.name)}</small></td><td><span data-no-translate>${esc(r.tariff_text)}</span><small>${esc(kinds[r.kind])}</small></td><td>${r.commission_cap === null ? "—" : `≤ ${esc(r.commission_cap)}%`}</td><td>${r.page}${r.continuation_page ? `–${r.continuation_page}` : ""}</td><td><button class="text-button" data-policy="${r.code}">Открыть</button></td></tr>`,
          )
          .join("") || '<tr><td colspan="5">Ничего не найдено</td></tr>';
      action("[data-policy]", (el) => details(entry(el.dataset.policy)));
    };
    $("[name=policy_search]").oninput = render;
    $("[name=policy_kind]").onchange = render;
    render();
    bindForm("#rnp-form", async (values) => {
      const result = await post("/policy/rnp/classify", readRnp(values) || {});
      $("#rnp-result").innerHTML =
        `<div class="notice"><strong><span>Учётная группа</span>: ${result.group || "—"}</strong><p>${esc(result.reason)}</p></div>`;
    });
  }
  function details(r) {
    const canConfigure = ![
      "components",
      "unspecified",
      "clarification",
    ].includes(r.kind);
    modal(
      `<h2 data-no-translate>${esc(r.code)} · ${esc(r.name)}</h2><p data-no-translate>${esc(r.tariff_text)}</p><p><span>Страница источника</span>: ${r.page}</p>${r.notes.map((n) => `<div class="notice" data-no-translate>${esc(n)}</div>`).join("")}<p class="form-hint">Проверка сравнивает проценты с документом. Комиссия проверяется отдельно и не прибавляется к тарифу.</p><form id="policy-check-form"><div class="form-grid">${r.kind === "components" ? r.components.map((c) => field(`component_${c.key}`, `${c.label}, %`, "", "number", 'required min="0" max="100" step="0.00000001"')).join("") : `${r.variants.length ? select("variant", "Вариант продукта", [["", "Выберите вариант"], ...r.variants.map((v) => [v.key, v.label])]) : ""}${field("rate", "Проверяемая ставка, %", "", "number", 'min="0" max="100" step="0.00000001"')}`}${field("commission", "Агентское вознаграждение, %", "", "number", 'min="0" max="100" step="0.00000001"')}</div><button type="submit" class="secondary">Проверить ограничения</button></form><div id="policy-check-result" aria-live="polite"></div>${state.user.role === "admin" && canConfigure ? '<button type="button" class="primary" id="configure-policy">Настроить версию тарифа</button>' : ""}`,
    );
    bindForm("#policy-check-form", async (values) => {
      const data = { code: r.code };
      if (values.variant) data.variant = values.variant;
      if (values.rate !== undefined && values.rate !== "")
        data.rate = values.rate;
      if (values.commission !== "") data.commission = values.commission;
      if (r.components.length)
        data.component_rates = Object.fromEntries(
          r.components.map((c) => [c.key, values[`component_${c.key}`]]),
        );
      const result = await post("/policy/check", data);
      $("#policy-check-result").innerHTML =
        result.checks
          .map(
            (c) =>
              `<div class="notice"><strong>${c.passed === true ? "✓" : c.passed === false ? "✕" : "—"} ${esc(c.label)}</strong><p>${esc(c.value ?? "—")}% · ${c.direction === "maximum" ? "≤" : "≥"} ${esc(c.bound ?? "—")}%</p></div>`,
          )
          .join("") + `<p class="form-hint">${esc(result.message)}</p>`;
    });
    if ($("#configure-policy"))
      $("#configure-policy").onclick = () =>
        productModal({
          code: r.code,
          name: r.name,
          policy_code: r.code,
          min_rate: r.minimum_rate ?? "",
          class_code:
            { "03": "vehicle", "08": "property", "09": "property" }[
              r.vertical
            ] || r.vertical,
          rate_type: ["fixed", "voyage"].includes(r.period_basis)
            ? "fixed"
            : "",
        });
  }
  function productFields(p) {
    return `<details ${p.policy_code || entry(p.code) ? "open" : ""}><summary>Источник тарифа INSON</summary><p class="form-hint">Для строк из каталога укажите действующие условия и основание расчёта. Дата документа не подставляется как дата начала действия.</p><div class="form-grid">${select("policy_code", "Код в исходной политике", [["", "Не применяется"], ...source.entries.map((r) => [r.code, `${r.code} · ${r.name}`])], p.policy_code || (entry(p.code) ? p.code : ""))}${select("policy_variant", "Вариант продукта", [["", "Не применяется"]])}${field("agent_commission_percent", "Агентское вознаграждение, %", p.agent_commission_percent ?? "", "number", 'min="0" max="100" step="0.00000001"')}${field("policy_basis_reference", "Основание базы ставки и даты действия", p.policy_basis_reference || "")}${field("policy_terms_reference", "Правила / программа / основной договор", p.policy_terms_reference || "")}${field("policy_approval_reference", "Документ согласования с ЦО", p.policy_approval_reference || "")}</div><label class="check"><input name="policy_current_confirmed" type="checkbox" ${p.policy_current_confirmed ? "checked" : ""}>Актуальность политики для этой версии подтверждена компанией</label><p id="policy-setup-note" class="form-hint"></p></details>`;
  }
  function bindProduct(p) {
    const form = $("#product-form");
    const code = $("[name=policy_code]", form),
      variant = $("[name=policy_variant]", form);
    function update(reset = false) {
      const r = entry(code.value);
      variant.innerHTML = [
        ["", "Не применяется"],
        ...(r?.variants || []).map((v) => [v.key, v.label]),
      ]
        .map(([v, l]) => `<option value="${esc(v)}">${esc(l)}</option>`)
        .join("");
      if (!reset) variant.value = p.policy_variant || "";
      $("#policy-setup-note").textContent = r
        ? `${r.tariff_text} · ${kinds[r.kind]}`
        : "";
      if (reset && r) {
        $("[name=min_rate]", form).value = r.minimum_rate ?? "";
        $("[name=policy_current_confirmed]", form).checked = false;
      }
    }
    code.onchange = () => update(true);
    variant.onchange = () => {
      const v = entry(code.value)?.variants.find(
        (v) => v.key === variant.value,
      );
      if (v) $("[name=min_rate]", form).value = v.minimum_rate;
    };
    update();
  }
  function readProduct(values, form) {
    for (const k of [
      "policy_code",
      "policy_variant",
      "agent_commission_percent",
    ])
      if (!values[k]) delete values[k];
    values.policy_current_confirmed = $(
      "[name=policy_current_confirmed]",
      form,
    ).checked;
    return values;
  }
  return {
    page,
    prepare,
    productFields,
    bindProduct,
    readProduct,
    rnpFields,
    readRnp,
  };
})();
