"use strict";
const $ = (s, root = document) => root.querySelector(s);
const $$ = (s, root = document) => [...root.querySelectorAll(s)];
const esc = (v) =>
  String(v ?? "").replace(
    /[&<>"']/g,
    (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[
        c
      ],
  );
const money = (v) =>
  v == null
    ? "Данные недоступны"
    : new Intl.NumberFormat("ru-RU", { maximumFractionDigits: 2 }).format(
        Number(v),
      );
const dateText = (v) => (v ? new Date(v).toLocaleDateString("ru-RU") : "—");
const today = () => new Date().toLocaleDateString("en-CA");
const state = {
  user: null,
  csrf: "",
  page: "surveys",
  products: [],
  templates: [],
  survey: null,
  locale: localStorage.getItem("surveyor-language") || "ru",
};
const translations = {
  ru: {
    surveys: "Осмотры",
    calculator: "Калькулятор",
    sources: "Открытые данные",
    admin: "Администрирование",
    profile: "Мой профиль",
    newSurvey: "Новый осмотр",
    workspace: "Рабочее пространство",
    subtitle: "Все документы, расчёты и решения — в одном месте.",
  },
  uz: {
    surveys: "Ko‘riklar",
    calculator: "Kalkulyator",
    sources: "Ochiq ma’lumotlar",
    admin: "Boshqaruv",
    profile: "Mening profilim",
    newSurvey: "Yangi ko‘rik",
    workspace: "Ish maydoni",
    subtitle: "Hujjatlar, hisob-kitoblar va qarorlar — bir joyda.",
  },
  en: {
    surveys: "Inspections",
    calculator: "Calculator",
    sources: "Public data",
    admin: "Administration",
    profile: "My profile",
    newSurvey: "New inspection",
    workspace: "Workspace",
    subtitle: "Documents, calculations and decisions in one place.",
  },
};
const t = (key) => translations[state.locale][key] || key;
const names = {
  draft: "Черновик",
  review: "На проверке",
  approved: "Утверждён",
  changes_requested: "Нужны правки",
  rejected: "Отклонён",
  annual: "Годовая",
  fixed: "Фиксированная",
  program: "По программе",
  normative: "По нормативному акту",
  employee: "Сотрудник",
  admin: "Администратор",
  actuary: "Актуарий",
  underwriter: "Андеррайтер",
  low: "Низкий",
  moderate: "Умеренный",
  high: "Высокий",
  unavailable: "Данные недоступны",
  confirmed: "Стоимость подтверждена",
  clarify: "Стоимость нужно уточнить",
  below_minimum: "Ниже минимума",
  above_market: "Выше рынка",
  within_range: "Внутри вилки",
  above_minimum_market_unavailable: "Не ниже минимума; рынок недоступен",
  visible_damage: "Видимые повреждения",
  poor_maintenance: "Плохое обслуживание",
  no_protection: "Нет защиты",
  hazardous_location: "Опасное расположение",
  insured_sum: "Страховая сумма",
  object_value: "Стоимость объекта",
  declared_rate: "Тариф, %",
  declared_premium: "Премия",
  term_days: "Срок, дней",
  extracted: "Распознано",
  blank: "Не заполнено",
  needs_review: "Нужна проверка",
  rules: "Текстовый слой",
  manual: "Ручная проверка",
};
Object.assign(names, {
  insured_organization: "Страхователь (организация)",
  insurer_organization: "Страховщик (организация)",
  contract_start: "Дата начала",
  contract_end: "Дата окончания",
  object_description: "Объект страхования",
});
const named = (v) => names[v] || v || "—";
function badge(status) {
  return `<span class="badge ${["approved", "confirmed", "low", "extracted"].includes(status) ? "green" : ["review", "clarify", "moderate", "manual"].includes(status) ? "amber" : ["high", "rejected", "below_minimum"].includes(status) ? "red" : ""}">${esc(named(status))}</span>`;
}
function toast(message, error = false) {
  const el = $("#toast");
  el.textContent = message;
  el.className = error ? "error" : "";
  el.hidden = false;
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => (el.hidden = true), 6000);
}
async function api(path, options = {}) {
  const headers = {
    ...(options.body instanceof FormData
      ? {}
      : { "Content-Type": "application/json" }),
    "X-CSRF-Token": state.csrf,
    ...options.headers,
  };
  const r = await fetch(`/api${path}`, { ...options, headers });
  const data = await r.json().catch(() => ({}));
  if (!r.ok) {
    if (r.status === 401 && state.user) {
      state.user = null;
      $("#workspace").hidden = true;
      $("#login-view").hidden = false;
    }
    throw new Error(data.detail || "Не удалось выполнить запрос");
  }
  return data;
}
const post = (path, body = {}) =>
  api(path, { method: "POST", body: JSON.stringify(body) });
function bindForm(id, handler) {
  const form = $(id);
  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const btn = $("button[type=submit]", form);
    if (btn) btn.disabled = true;
    try {
      await handler(Object.fromEntries(new FormData(form)), form);
    } catch (err) {
      toast(err.message, true);
      const error = $(".form-error", form);
      if (error) error.textContent = err.message;
    } finally {
      if (btn) btn.disabled = false;
    }
  });
}
function action(selector, handler) {
  $$(selector).forEach((el) =>
    el.addEventListener("click", async (e) => {
      e.preventDefault();
      el.disabled = true;
      try {
        await handler(el);
      } catch (err) {
        toast(err.message, true);
      } finally {
        el.disabled = false;
      }
    }),
  );
}
function field(name, label, value = "", type = "text", extra = "") {
  return `<label>${esc(label)}<input name="${esc(name)}" type="${type}" value="${esc(value)}" ${extra}></label>`;
}
function select(name, label, options, value = "") {
  return `<label>${esc(label)}<select name="${name}">${options.map(([v, l]) => `<option value="${esc(v)}" ${v === value ? "selected" : ""}>${esc(l)}</option>`).join("")}</select></label>`;
}
function jsonDetails(data, title = "Подробности и источники") {
  return `<details><summary>${esc(title)}</summary><pre class="details">${esc(JSON.stringify(data, null, 2))}</pre></details>`;
}
function heading(title, subtitle = "", button = "") {
  return `<div class="page-heading"><div><span class="eyebrow">${esc(t("workspace").toUpperCase())}</span><h1>${esc(title)}</h1><p>${esc(subtitle)}</p></div>${button}</div>`;
}
function modal(html) {
  $("#modal-content").innerHTML = html;
  $("#modal").showModal();
}
$("#modal-close").onclick = () => $("#modal").close();
$("#locale").value = state.locale;
$("#locale").onchange = async (e) => {
  state.locale = e.target.value;
  localStorage.setItem("surveyor-language", state.locale);
  renderNav();
  await navigate(state.page);
};

function renderNav() {
  const items = [
    ["surveys", "▧"],
    ["calculator", "⌗"],
    ["sources", "◎"],
  ];
  if (["admin", "actuary"].includes(state.user.role))
    items.push(["admin", "⚙"]);
  items.push(["profile", "◯"]);
  $("#navigation").innerHTML = items
    .map(
      ([p, i]) =>
        `<button data-nav="${p}" class="${state.page === p ? "active" : ""}"><span class="nav-icon">${i}</span>${esc(t(p))}</button>`,
    )
    .join("");
  action("[data-nav]", (el) => navigate(el.dataset.nav));
  $("#user-chip").textContent = state.user.name;
}
async function enter(data) {
  state.user = data.user;
  state.csrf = data.csrf;
  $("#login-view").hidden = true;
  $("#workspace").hidden = false;
  $("#demo-banner").hidden = data.data_mode === "real";
  renderNav();
  if (state.user.must_change_password) {
    return changePassword();
  }
  state.products = await api("/products");
  state.templates = await api("/templates");
  await navigate("surveys");
}
async function navigate(page) {
  state.page = page;
  renderNav();
  $("#breadcrumb").textContent = t(page);
  $("#content").innerHTML = '<div class="loading">Загрузка…</div>';
  try {
    await {
      surveys: dashboard,
      calculator: calculator,
      sources: sourcesPage,
      admin: () => adminPage("products"),
      profile: profilePage,
    }[page]();
  } catch (err) {
    $("#content").innerHTML =
      `<div class="error-box">${esc(err.message)}</div>`;
  }
}
bindForm("#login-form", async (data) => enter(await post("/auth/login", data)));
$("#logout").onclick = async () => {
  try {
    await post("/auth/logout");
    location.reload();
  } catch (err) {
    toast(err.message, true);
  }
};
function changePassword() {
  $("#content").innerHTML =
    heading("Смена пароля", "При первом входе задайте личный пароль.") +
    `<section class="panel"><form id="password-form"><div class="form-grid">${field("old_password", "Текущий пароль", "", "password", 'required autocomplete="current-password"')}${field("new_password", "Новый пароль (от 8 символов)", "", "password", 'required minlength="8" autocomplete="new-password"')}</div><button type="submit" class="primary">Сохранить пароль</button></form></section>`;
  bindForm("#password-form", async (d) => {
    const result = await post("/auth/password", d);
    toast("Пароль изменён");
    await enter(result);
  });
}

async function dashboard() {
  const rows = await api("/surveys");
  $("#content").innerHTML =
    heading(
      t("surveys"),
      t("subtitle"),
      `<button id="new-survey" class="primary">＋ ${esc(t("newSurvey"))}</button>`,
    ) +
    `<div class="metrics"><div class="metric"><div class="label">Всего осмотров</div><div class="value">${rows.length.toString().padStart(2, "0")}</div><small>В вашем рабочем пространстве</small></div><div class="metric"><div class="label">Ожидают решения</div><div class="value">${rows
      .filter((r) => r.status === "review")
      .length.toString()
      .padStart(
        2,
        "0",
      )}</div><small>На проверке у андеррайтера</small></div><div class="metric"><div class="label">Утверждены</div><div class="value">${rows
      .filter((r) => r.status === "approved")
      .length.toString()
      .padStart(
        2,
        "0",
      )}</div><small>С зафиксированным решением</small></div></div><section class="panel"><div class="panel-head"><h3>Журнал осмотров</h3><span class="muted small">Последние 200 записей</span></div>${rows.length ? `<div class="table-wrap"><table><thead><tr><th>ОБЪЕКТ</th><th>ДАТА СОЗДАНИЯ</th><th>СТАТУС</th><th></th></tr></thead><tbody>${rows.map((r) => `<tr><td><button class="link-button" data-open="${r.id}">${esc(r.title)}</button><small>№ ${r.id.slice(0, 8)} · версия ${r.revision}</small></td><td>${dateText(r.created_at)}</td><td>${badge(r.status)}</td><td><button class="text-button" data-open="${r.id}">↗</button></td></tr>`).join("")}</tbody></table></div>` : '<div class="empty"><div class="empty-symbol">▧</div><h3>Начните с первого осмотра</h3><p>Загрузите документы, проверьте данные<br>и получите акт с прозрачным расчётом.</p></div>'}</section><div class="app-footer"><span>Каждая цифра имеет источник. Каждое решение — автора.</span><span>Не является кредитным скорингом</span></div>`;
  $("#new-survey").onclick = () => {
    modal(
      `<h2>Новый осмотр</h2><p class="muted">Дайте объекту понятное название.</p><form id="create-survey">${field("title", "Название осмотра", "", "text", 'required maxlength="200" placeholder="Например: Учебный автомобиль № 01"')}<button type="submit" class="primary">Создать осмотр →</button></form>`,
    );
    bindForm("#create-survey", async (d) => {
      const row = await post("/surveys", d);
      $("#modal").close();
      await openSurvey(row.id);
    });
  };
  action("[data-open]", (el) => openSurvey(el.dataset.open));
}
async function openSurvey(id, step = "files") {
  state.survey = await api(`/surveys/${id}`);
  renderSurvey(step);
}
function surveyFrame(step) {
  const s = state.survey;
  return (
    heading(
      s.title,
      `Осмотр № ${s.id.slice(0, 8)} · ${named(s.status)}`,
      `<button class="secondary" id="back-surveys">← Все осмотры</button>`,
    ) +
    `<div class="steps">${[
      ["files", "Фото и документы"],
      ["review", "Проверить"],
      ["report", "Акт"],
    ]
      .map(
        ([key, name], i) =>
          `<button data-step="${key}" class="${step === key ? "active" : ""}"><span>${i + 1}</span>${name}</button>`,
      )
      .join("")}</div><div id="survey-body"></div>`
  );
}
function renderSurvey(step) {
  $("#content").innerHTML = surveyFrame(step);
  $("#back-surveys").onclick = () => navigate("surveys");
  action("[data-step]", (el) => renderSurvey(el.dataset.step));
  if (step === "files") renderFiles();
  if (step === "review") renderReview();
  if (step === "report") renderReportList();
}
function renderFiles() {
  const s = state.survey;
  $("#survey-body").innerHTML =
    `<div class="two-col"><section class="panel"><div class="panel-head"><h3>Материалы осмотра</h3><span class="muted small">${s.documents.length} / 20 файлов</span></div>${s.owner_id === state.user.id ? `<form id="upload-form"><div class="upload-zone"><span class="empty-symbol">↑</span><strong>Добавьте фото, договор или запрос филиала</strong><p class="muted small">PDF, Word, Excel, TXT, CSV, JPG, PNG, WEBP<br>До 15 МБ на файл · PDF до 50 страниц</p><input type="file" name="file" multiple required accept=".pdf,.docx,.xlsx,.txt,.csv,.jpg,.jpeg,.png,.webp"></div><button type="submit" class="secondary">Загрузить выбранные файлы</button></form>` : ""}<div class="notice">Фото и сканы не распознаются автоматически: ИИ отключён. После загрузки проверьте их вручную.</div>${s.documents
      .map(
        (d) =>
          `<div class="file-card"><h4><a href="/api/documents/${d.id}/download">${esc(d.filename)} ↗</a></h4>${badge(d.extracted.mode)}<p class="small muted">${esc(d.extracted.notice)}</p><div>${Object.entries(
            d.extracted.fields,
          )
            .map(
              ([k, v]) =>
                `<div class="field-row"><span>${esc(named(k))}</span><span>${v.value === null ? esc(named(v.status)) : esc(v.value)} <small class="muted">· ${esc(v.source)}</small></span></div>`,
            )
            .join("")}</div></div>`,
      )
      .join(
        "",
      )}<div class="actions"><button class="primary" id="to-review">Проверить данные →</button></div></section><aside><section class="panel"><span class="section-title">КАК ЭТО РАБОТАЕТ</span><h3>Факты остаются фактами</h3><p class="small muted">Текстовые документы читаются правилами. У каждого извлечённого значения сохраняется имя файла и исходная строка.</p><p class="small muted">Ваши правки показываются отдельно. Расхождения между документами попадут в акт.</p></section></aside></div>`;
  if ($("#upload-form"))
    bindForm("#upload-form", async (_, form) => {
      const files = $("input[type=file]", form).files;
      for (const file of files) {
        const data = new FormData();
        data.append("file", file);
        await api(`/surveys/${s.id}/documents`, { method: "POST", body: data });
      }
      toast("Файлы загружены");
      await openSurvey(s.id);
    });
  $("#to-review").onclick = () => renderSurvey("review");
}
function productOptions() {
  return state.products.map((p) => [
    p.code,
    `${p.code} · ${p.name} (${named(p.rate_type)})`,
  ]);
}
function basicFields(d = {}) {
  return `${select("product_code", "Продукт", productOptions(), d.product_code || state.products[0]?.code)}${field("region", "Регион", d.region || "Ташкент", "text", 'required maxlength="100"')}${field("insured_sum", "Страховая сумма, UZS", d.insured_sum || "", "number", 'required min="0.01" step="0.01"')}${field("object_value", "Стоимость объекта, UZS", d.object_value || "", "number", 'required min="0.01" step="0.01"')}${field("term_days", "Срок страхования, дней", d.term_days || 365, "number", 'required min="1" max="36500"')}${field("tariff_date", "Дата применения тарифа", d.tariff_date || today(), "date", "required")}${select(
    "object_type",
    "Вид объекта",
    [
      ["vehicle", "Автомобиль"],
      ["equipment", "Оборудование"],
      ["housing", "Жильё / техника"],
      ["large", "Крупный объект"],
      ["other", "Другое"],
    ],
    d.object_type || "other",
  )}${field("program", "Программа (если применимо)", d.program || "")}`;
}
function renderReview() {
  const s = state.survey,
    d = s.inputs || {};
  const extracted = {};
  for (const doc of s.documents)
    for (const [key, item] of Object.entries(doc.extracted.fields))
      if (item.value && !extracted[key]) extracted[key] = item.value;
  const inputs = { ...extracted, ...d };
  $("#survey-body").innerHTML =
    `<form id="review-form"><div class="two-col"><div><section class="panel"><div class="panel-head"><h3>Объект и условия</h3><span class="badge">Ручная проверка</span></div><div class="form-grid">${basicFields(inputs)}<label class="span-2">Описание объекта<textarea name="object_description" maxlength="2000">${esc(inputs.object_description || "")}</textarea></label></div><p class="form-hint">Четыре основных поля: продукт, страховая сумма, стоимость, регион. Срок нужен для годовой ставки и сравнения с рынком.</p><h3>Признаки риска</h3><div class="feature-list" id="features"></div></section><section class="panel"><h3>Сверка документов</h3><div class="form-grid">${field("declared_rate", "Тариф из запроса / договора, %", inputs.declared_rate || "", "number", 'min="0" max="100" step="0.000001"')}${field("declared_premium", "Премия из запроса / договора, UZS", inputs.declared_premium || "", "number", 'min="0" step="0.01"')}</div>${
      Object.keys(extracted).length
        ? `<p class="form-hint">Из документа: ${Object.entries(extracted)
            .map(([k, v]) => `${esc(named(k))} = ${esc(v)}`)
            .join(" · ")}</p>`
        : ""
    }<label>Причина исправлений распознанных значений<textarea name="override_reason" placeholder="Если исправили значение документа — объясните почему">${esc(d.override_reason || "")}</textarea></label></section><section class="panel"><h3>Оценка стоимости</h3><p class="form-hint">Сопоставимые предложения: то же изделие, цена и дата обязательны, не старше 6 месяцев. Медиана до ручных правок сохраняется рядом с оценкой.</p><div id="comparables"></div><button type="button" class="secondary" id="add-comparable">＋ Сопоставимое предложение</button><details><summary>Оборудование: цена покупки и износ</summary><div class="form-grid">${field("purchase_price", "Цена покупки, UZS", d.purchase_price || "", "number", 'min="0" step="0.01"')}${field("depreciation_percent", "Износ, %", d.depreciation_percent || 0, "number", 'min="0" max="100" step="0.01"')}</div></details><details><summary>Крупный объект: отчёт оценщика + второй метод</summary><div class="form-grid">${field("appraiser_value", "Оценка, UZS", d.appraiser_value || "", "number", 'min="0"')}${field("appraiser_source", "Источник оценки", d.appraiser_source || "")}${field("appraiser_date", "Дата оценки", d.appraiser_date || "", "date")}${field("second_method_value", "Второй метод, UZS", d.second_method_value || "", "number", 'min="0"')}${field("second_method_source", "Источник второго метода", d.second_method_source || "")}${field("second_method_date", "Дата второго метода", d.second_method_date || "", "date")}</div></details></section></div><aside><section class="panel"><span class="section-title">ПЕРЕД ФОРМИРОВАНИЕМ</span><h3>Проверьте исходные данные</h3><p class="muted small">Расчёт использует версию тарифа на выбранную дату. Все введённые сотрудником значения отмечаются в акте.</p>${select(
      "language",
      "Язык заголовков акта",
      [
        ["ru", "Русский"],
        ["uz", "O‘zbekcha"],
        ["en", "English"],
      ],
      d.language || state.locale,
    )}<p class="form-hint">Тексты источников и оговорок сохраняются на исходном языке.</p><label class="check"><input name="manual_review_confirmed" type="checkbox" required ${d.manual_review_confirmed ? "checked" : ""}>Я проверил(а) документы, суммы, сроки и фотографии.</label><button type="submit" class="primary full" ${s.owner_id !== state.user.id ? "disabled" : ""}>Сохранить и сформировать →</button><p class="form-error"></p></section><div class="notice">Страховой балл не является кредитным скорингом. Окончательное решение принимает андеррайтер.</div></aside></div></form>`;
  const renderFeatures = () => {
    const code = $("[name=product_code]").value;
    const p = state.products.find((p) => p.code === code);
    const template = state.templates.find(
      (t) => t.class_code === p?.class_code,
    );
    $("#features").innerHTML =
      Object.keys(template?.feature_weights || {})
        .map(
          (k) =>
            `<label><input type="checkbox" name="feature" value="${esc(k)}" ${(d.features || []).includes(k) ? "checked" : ""}>${esc(named(k))}</label>`,
        )
        .join("") ||
      '<p class="muted small">Для класса пока нет шаблона риска.</p>';
  };
  renderFeatures();
  $("[name=product_code]").onchange = renderFeatures;
  for (const c of d.comparables || []) addComparable(c);
  $("#add-comparable").onclick = () => addComparable();
  bindForm("#review-form", async (values, form) => {
    const body = surveyBody(values);
    body.revision = s.revision;
    body.features = $$("input[name=feature]:checked", form).map((x) => x.value);
    body.manual_review_confirmed = true;
    body.comparables = $$(".comparable").map((el) => {
      const obj = {};
      $$("input,select", el).forEach(
        (x) =>
          (obj[x.dataset.key] = x.type === "checkbox" ? x.checked : x.value),
      );
      if (!obj.original_price) obj.original_price = obj.price;
      return obj;
    });
    body.overrides = {};
    for (const [key, value] of Object.entries(extracted))
      if (
        body[key] != null &&
        (Number.isFinite(Number(value))
          ? Number(body[key]) !== Number(value)
          : String(body[key]) !== String(value))
      )
        body.overrides[key] = String(body[key]);
    const result = await api(`/surveys/${s.id}`, {
      method: "PUT",
      body: JSON.stringify(body),
    });
    s.revision = result.revision;
    const report = await post(`/surveys/${s.id}/reports`);
    state.survey = await api(`/surveys/${s.id}`);
    renderSurvey("report");
    await showReport(report.id);
    toast("Акт сформирован");
  });
}
function addComparable(c = {}) {
  const el = document.createElement("div");
  el.className = "comparable";
  el.innerHTML = `<div class="form-grid">${[
    ["label", "Изделие", "text"],
    ["price", "Цена", "number"],
    ["original_price", "Цена до правок", "number"],
    ["date", "Дата", "date"],
    ["source", "Ссылка / файл источника", "text"],
    ["currency", "Валюта", "text"],
    ["edit_reason", "Причина правки", "text"],
  ]
    .map(
      ([key, label, type]) =>
        `<label>${label}<input data-key="${key}" type="${type}" value="${esc(c[key] || (key === "currency" ? "UZS" : ""))}" ${["label", "price", "date", "source", "currency"].includes(key) ? "required" : ""} ${type === "number" ? 'min="0.01" step="0.01"' : ""}></label>`,
    )
    .join(
      "",
    )}</div><label class="check"><input data-key="same_item" type="checkbox" ${c.same_item !== false ? "checked" : ""}>То же изделие / сопоставимый объект</label><button class="text-button danger-button" type="button">Удалить предложение</button>`;
  $("button", el).onclick = () => el.remove();
  $("#comparables").append(el);
}
function surveyBody(values) {
  const keys = [
    "product_code",
    "region",
    "insured_sum",
    "object_value",
    "term_days",
    "tariff_date",
    "object_type",
    "program",
    "object_description",
    "declared_rate",
    "declared_premium",
    "purchase_price",
    "depreciation_percent",
    "appraiser_value",
    "appraiser_source",
    "appraiser_date",
    "second_method_value",
    "second_method_source",
    "second_method_date",
    "override_reason",
    "language",
  ];
  const body = { revision: 1 };
  for (const k of keys)
    if (values[k] !== "" && values[k] != null)
      body[k] = k === "term_days" ? Number(values[k]) : values[k];
  return body;
}
function renderReportList() {
  const s = state.survey;
  $("#survey-body").innerHTML =
    `<section class="panel"><h3>Версии акта</h3>${s.reports.length ? s.reports.map((r) => `<div class="field-row"><span>${dateText(r.created_at)} · № ${r.id.slice(0, 8)}</span><button class="link-button" data-report="${r.id}">Открыть акт →</button></div>`).join("") : '<div class="empty"><p>Заполните и подтвердите данные на шаге «Проверить».</p></div>'}</section><div id="report-view"></div>`;
  action("[data-report]", (el) => showReport(el.dataset.report));
  if (s.reports[0])
    showReport(s.reports[0].id).catch((e) => toast(e.message, true));
}
function calculationView(c) {
  if (c.status !== "calculated")
    return `<div class="notice">${esc(c.reason)}</div>`;
  return `<div class="result-card"><span class="eyebrow">РАСЧЁТНАЯ СТРАХОВАЯ ПРЕМИЯ</span><div class="result-value">${money(c.premium)} <small>UZS</small></div><small>${esc(named(c.rate_type))} ставка · ${c.term_days} дней · ${esc(c.formula)}</small><div class="result-grid"><div><small>Минимальная</small><strong>${c.minimum_rate}%</strong></div><div><small>Рекомендуемая</small><strong>${c.recommended_rate}%</strong></div><div><small>Рыночная, годовая</small><strong>${c.annual_market_rate === null ? "—" : c.annual_market_rate + "%"}</strong></div></div></div><p class="report-note">Годовой эквивалент рекомендации: ${c.annualized_rate}%. Рыночная ставка всегда сравнивается в годовом выражении.</p>${c.warnings.map((w) => `<div class="notice">${esc(w)}</div>`).join("")}`;
}
async function showReport(id) {
  const report = await api(`/reports/${id}`),
    s = report.snapshot,
    c = s.calculation,
    v = s.valuation;
  $("#report-view").innerHTML =
    `<div class="actions"><a class="secondary" href="/api/reports/${id}/export/docx">↓ Word</a><a class="secondary" href="/api/reports/${id}/export/pdf">↓ PDF</a><button class="primary" id="send-telegram">Отправить себе в Telegram ↗</button></div><p class="report-note">Акт № ${id.slice(0, 8)} · ${dateText(report.created_at)} · Подлежит подтверждению андеррайтером · Не является кредитным скорингом</p>${calculationView(c)}<section class="panel"><div class="report-section"><h3>1. Объект и документы</h3><div class="form-grid"><div>${esc(s.title)}<p class="muted small">${esc(s.inputs.region)} · ${esc(s.inputs.object_description)}</p></div><div>Страховая сумма: ${money(s.inputs.insured_sum)} UZS<br>Стоимость объекта: ${money(s.inputs.object_value)} UZS</div></div>${jsonDetails(s.documents, "Документы и происхождение значений")}${jsonDetails(s.conflicts, "Расхождения источников")}${jsonDetails({ overrides: s.inputs.overrides, reason: s.inputs.override_reason }, "Ручные исправления")}</div><div class="report-section"><h3>2. Оценка стоимости</h3>${badge(v.status)}<p>Оценка: ${money(v.estimate)} UZS · Медиана до правок: ${money(v.raw_median)} UZS</p>${jsonDetails(v, "Предложения, источники и исключённые цены")}</div><div class="report-section"><h3>3. Тариф и страховая премия</h3><p class="small">Источник: тарифная политика ${esc(s.product.code)}, версия от ${esc(s.product.effective_from)}.</p><p class="small">Сверка: ${esc(named(c.comparison))}. Отклонение премии: ${money(c.premium_discrepancy)} UZS.</p>${jsonDetails(c, "Формула и все значения расчёта")}</div><div class="report-section"><h3>4. Аналитика риска</h3><p>Уровень риска: ${badge(c.risk_level)} · Страховой балл: ${c.risk_score ?? "—"}</p>${jsonDetails(s.losses, "Убытки за три полных года")}${jsonDetails(s.indicators, "Открытые данные: ссылки, периоды и актуальность")}${jsonDetails(s.calibration, "Утверждение актуария")}</div><div class="report-section"><h3>5. Заключение и оговорки</h3>${[...s.disclaimers, ...s.clauses, ...s.checklist].map((x) => `<p class="report-note">${esc(x)}</p>`).join("")}</div></section><section class="panel"><h3>Решение андеррайтера</h3>${report.decisions.map((d) => `<div class="file-card">${badge(d.data.decision)}<p>${esc(d.data.comment)}</p><small>${dateText(d.created_at)} · ${esc(d.user_id)}</small></div>`).join("") || '<p class="muted small">Решение ещё не принято.</p>'}${
      state.user.role === "underwriter"
        ? `<form id="decision-form">${select("decision", "Решение", [
            ["changes_requested", "Нужны правки"],
            ["approved", "Утвердить"],
            ["rejected", "Отклонить"],
          ])}<label>Комментарий<textarea name="comment" required minlength="3"></textarea></label><button type="submit" class="primary">Зафиксировать решение</button></form>`
        : ""
    }</section>`;
  $("#send-telegram").onclick = async () => {
    try {
      await post(`/reports/${id}/telegram`);
      toast("PDF отправлен");
    } catch (e) {
      toast(e.message, true);
    }
  };
  if ($("#decision-form"))
    bindForm("#decision-form", async (d) => {
      await post(`/reports/${id}/decision`, d);
      await showReport(id);
      toast("Решение сохранено");
    });
}
async function calculator() {
  $("#content").innerHTML =
    heading(
      t("calculator"),
      "Проверка премии по действующей тарифной политике.",
    ) +
    `<div class="two-col"><section class="panel"><h3>Параметры расчёта</h3><form id="calculator-form"><div class="form-grid">${basicFields()}</div><button type="submit" class="primary">Рассчитать премию →</button></form></section><aside id="calculator-result"><section class="panel"><h3>Срок имеет значение</h3><p class="small muted">Годовая ставка: сумма × ставка × дни / 365.<br>Фиксированная: сумма × ставка.</p><p class="small muted">Для ОСГОР используйте продукт с типом «По нормативному акту». Тариф и источник задаёт администратор.</p></section></aside></div>`;
  bindForm("#calculator-form", async (d) => {
    $("#calculator-result").innerHTML = calculationView(
      await post("/calculate", surveyBody(d)),
    );
  });
}
async function profilePage() {
  $("#content").innerHTML =
    heading(t("profile")) +
    `<section class="panel"><h3>${esc(state.user.name)}</h3><p>${esc(named(state.user.role))} · ${esc(state.user.branch)}</p><p>Telegram ID: ${esc(state.user.telegram_id || "Не привязан")}</p><div class="actions"><button id="change-password" class="secondary">Сменить пароль</button>${window.Telegram?.WebApp?.initData ? '<button id="link-telegram" class="primary">Привязать текущий Telegram</button>' : '<span class="muted small">Для привязки откройте приложение в Telegram или попросите администратора указать ваш ID.</span>'}</div></section>`;
  $("#change-password").onclick = changePassword;
  if ($("#link-telegram"))
    $("#link-telegram").onclick = async () => {
      try {
        const d = await post("/auth/telegram/link", {
          init_data: window.Telegram.WebApp.initData,
        });
        state.user = d.user;
        toast("Telegram привязан");
        profilePage();
      } catch (e) {
        toast(e.message, true);
      }
    };
}
async function sourcesPage() {
  const data = await api("/sources");
  $("#content").innerHTML =
    heading(
      t("sources"),
      "У каждого показателя — источник, период и история версий.",
      ["admin", "actuary"].includes(state.user.role)
        ? '<button class="primary" id="collect-cbu">Обновить курс CBU ↻</button>'
        : "",
    ) +
    `<section class="panel"><h3>Реестр каналов</h3><div class="table-wrap"><table><thead><tr><th>ИСТОЧНИК</th><th>СПОСОБ ДОСТУПА</th><th>ПОСЛЕДНЯЯ ПРОВЕРКА</th></tr></thead><tbody>${data.channels.map((c) => `<tr><td><strong>${esc(c.data.domain)}</strong><small>${esc(c.data.note)}</small></td><td><span class="badge ${c.enabled ? "green" : "amber"}">${esc(c.enabled ? "Подключён" : c.data.access)}</span>${c.error ? `<small class="form-error">${esc(c.error)}</small>` : ""}</td><td>${dateText(c.last_success)}</td></tr>`).join("")}</tbody></table></div></section><section class="panel"><h3>Сохранённые показатели</h3>${data.indicators.length ? data.indicators.map((i) => `<div class="file-card"><strong>${esc(i.metric)} · ${money(i.value)} ${esc(i.unit)}</strong> ${i.stale ? '<span class="badge amber">Устарели</span>' : ""}<p class="small muted">${esc(i.region)} · ${esc(i.period)} · <a href="${esc(i.source_url)}" target="_blank" rel="noopener noreferrer">Источник ↗</a> · Получено ${dateText(i.fetched_at)}</p>${state.user.role === "actuary" && !i.approved_by ? `<button class="secondary" data-approve-indicator="${i.id}">Утвердить поправку</button>` : ""}</div>`).join("") : '<p class="muted small">Показатели ещё не загружены. Расчёт не подставляет вымышленные значения.</p>'}</section>`;
  if ($("#collect-cbu"))
    action("#collect-cbu", async () => {
      const r = await post("/admin/sources/cbu/collect");
      toast(
        r.status === "error" ? r.message : "Курсы обновлены",
        r.status === "error",
      );
      await sourcesPage();
    });
  action("[data-approve-indicator]", async (el) => {
    await post(`/admin/indicators/${el.dataset.approveIndicator}/approve`);
    await sourcesPage();
  });
}

async function adminPage(tab) {
  if (state.user.role === "actuary" && tab === "products") tab = "losses";
  const tabs =
    state.user.role === "admin"
      ? [
          ["products", "Продукты и тарифы"],
          ["employees", "Сотрудники"],
          ["losses", "Страховые случаи"],
          ["templates", "Шаблоны классов"],
          ["indicators", "Показатели"],
          ["audit", "Журнал действий"],
        ]
      : [
          ["losses", "Страховые случаи"],
          ["templates", "Шаблоны классов"],
          ["indicators", "Показатели"],
        ];
  $("#content").innerHTML =
    heading(t("admin"), "Справочники и настройки расчётного ядра.") +
    `<div class="admin-tabs">${tabs.map(([k, l]) => `<button data-tab="${k}" class="${tab === k ? "active" : ""}">${l}</button>`).join("")}</div><div id="admin-content"></div>`;
  action("[data-tab]", (el) => adminPage(el.dataset.tab));
  await {
    products: adminProducts,
    employees: adminEmployees,
    losses: adminLosses,
    templates: adminTemplates,
    indicators: adminIndicators,
    audit: adminAudit,
  }[tab]();
}
async function adminProducts() {
  const rows = await api("/products?history=true");
  $("#admin-content").innerHTML =
    `<section class="panel"><div class="panel-head"><h3>Версии тарифной политики</h3><button class="primary" id="add-product">＋ Продукт / новая версия</button></div><div class="table-wrap"><table><thead><tr><th>ПРОДУКТ</th><th>КЛАСС</th><th>СТАВКА / МИНИМУМ</th><th>ТИП</th><th>ДЕЙСТВУЕТ С</th><th></th></tr></thead><tbody>${rows.map((r) => `<tr><td>${esc(r.code)}<small>${esc(r.name)}</small></td><td>${esc(r.class_code)}</td><td>${r.rate}% / ${r.min_rate}%</td><td>${badge(r.rate_type)}</td><td>${esc(r.effective_from)}</td><td><button class="text-button" data-version="${r.id}">Новая версия ↗</button></td></tr>`).join("")}</tbody></table></div></section><section class="panel"><h3>Импорт из Excel / CSV</h3><p class="form-hint">Обязательные столбцы: code, name, class_code, rate, min_rate, rate_type, effective_from. Типы: annual, fixed, program, normative.<br>Сначала показывается предпросмотр. Существующие версии не перезаписываются.</p><form id="import-form"><input name="file" type="file" accept=".csv,.xlsx" required><button type="submit" class="secondary">Предпросмотр импорта</button></form><div id="import-preview"></div></section>`;
  $("#add-product").onclick = () => productModal();
  action("[data-version]", (el) =>
    productModal(rows.find((r) => r.id === el.dataset.version)),
  );
  bindImport("products");
}
function productModal(p = {}) {
  modal(
    `<h2>${p.id ? "Новая версия тарифа" : "Добавить продукт"}</h2><form id="product-form"><div class="form-grid">${field("code", "Код", p.code || "", "text", "required")}${field("name", "Название", p.name || "", "text", "required")}${field("class_code", "Класс", p.class_code || "property", "text", "required")}${field("effective_from", "Дата начала действия", p.id ? today() : p.effective_from || today(), "date", "required")}${field("rate", "Ставка, %", p.rate || "", "number", 'required min="0" max="100" step="0.000001"')}${field("min_rate", "Минимум, %", p.min_rate || "", "number", 'required min="0" max="100" step="0.000001"')}${select(
      "rate_type",
      "Тип ставки",
      [
        ["annual", "Годовая"],
        ["fixed", "Фиксированная"],
        ["program", "По программе"],
        ["normative", "По нормативному акту"],
      ],
      p.rate_type || "annual",
    )}${select(
      "program_basis",
      "База программ",
      [
        ["annual", "Годовая"],
        ["fixed", "Фиксированная"],
      ],
      p.program_basis || "annual",
    )}${select(
      "normative_basis",
      "Нормативная база",
      [
        ["", "Не применяется"],
        ["annual", "Годовая"],
        ["fixed", "Фиксированная"],
      ],
      p.normative_basis || "",
    )}${field("normative_source", "Ссылка на нормативный акт", p.normative_source || "", "url")}<label class="span-2">Ставки программ (JSON: название → процент)<textarea name="program_rates">${esc(JSON.stringify(p.program_rates || {}))}</textarea></label></div><p class="form-hint">Ставки хранятся в процентах: 0.5 означает 0,5%. Изменение создаёт новую версию.</p><button type="submit" class="primary">Сохранить версию</button></form>`,
  );
  bindForm("#product-form", async (d) => {
    d.program_rates = JSON.parse(d.program_rates);
    if (!d.normative_basis) delete d.normative_basis;
    if (!d.normative_source) delete d.normative_source;
    await post("/admin/products", d);
    $("#modal").close();
    state.products = await api("/products");
    await adminProducts();
    toast("Версия тарифа сохранена");
  });
}
function bindImport(kind) {
  bindForm("#import-form", async (_, form) => {
    const fd = new FormData();
    fd.append("file", $("input", form).files[0]);
    const batch = await api(`/admin/imports/${kind}/preview`, {
      method: "POST",
      body: fd,
    });
    $("#import-preview").innerHTML =
      `<div class="notice">Строк: ${batch.rows.length} · Добавить: ${batch.rows.filter((r) => r.action === "add").length} · Изменить: ${batch.rows.filter((r) => r.action === "update").length} · Ошибок: ${batch.rows.filter((r) => r.action === "error").length}</div>${jsonDetails(batch.rows, "Строки импорта")}<button class="primary" id="confirm-import" ${batch.can_confirm ? "" : "disabled"}>Подтвердить сохранение</button>`;
    action("#confirm-import", async () => {
      await post(`/admin/imports/${batch.id}/confirm`);
      toast("Импорт сохранён");
      state.products = await api("/products");
      await adminPage(kind);
    });
  });
}
async function adminEmployees() {
  const rows = await api("/admin/employees");
  $("#admin-content").innerHTML =
    `<section class="panel"><div class="panel-head"><h3>Доступ сотрудников</h3><button class="primary" id="add-employee">＋ Добавить сотрудника</button></div><div class="table-wrap"><table><thead><tr><th>СОТРУДНИК</th><th>РОЛЬ</th><th>ФИЛИАЛ</th><th>СТАТУС</th><th></th></tr></thead><tbody>${rows.map((u) => `<tr><td>${esc(u.name)}<small>${esc(u.login)} · ${esc(u.phone)}</small><small>Telegram: ${esc(u.telegram_id || "—")}</small></td><td>${esc(named(u.role))}</td><td>${esc(u.branch || "—")}</td><td>${badge(u.active ? "approved" : "rejected")}</td><td>${u.id !== state.user.id ? `<button class="text-button" data-user="${u.id}">Изменить</button>` : ""}</td></tr>`).join("")}</tbody></table></div></section>`;
  $("#add-employee").onclick = () => {
    modal(
      `<h2>Новый сотрудник</h2><form id="employee-form"><div class="form-grid">${field("name", "Ф.И.О.", "", "text", "required")}${field("position", "Должность")}${field("department", "Департамент / отдел")}${field("branch", "Филиал")}${field("login", "Логин", "", "text", 'required minlength="3"')}${field("password", "Временный пароль", "", "password", 'required minlength="8" autocomplete="new-password"')}${field("phone", "Телефон (+998...)", "", "tel", "required")}${select(
        "role",
        "Роль",
        [
          ["employee", "Сотрудник"],
          ["underwriter", "Андеррайтер"],
          ["actuary", "Актуарий"],
          ["admin", "Администратор"],
        ],
      )}${field("telegram_id", "Telegram ID (необязательно)")}</div><div class="notice">При первом входе сотрудник обязан сменить пароль. Только актуарий утверждает калибровку; только андеррайтер — акт.</div><button type="submit" class="primary">Создать сотрудника</button></form>`,
    );
    bindForm("#employee-form", async (d) => {
      if (!d.telegram_id) delete d.telegram_id;
      await post("/admin/employees", d);
      $("#modal").close();
      await adminEmployees();
      toast("Сотрудник создан");
    });
  };
  action("[data-user]", (el) => {
    const u = rows.find((x) => x.id === el.dataset.user);
    modal(
      `<h2>${esc(u.name)}</h2><form id="edit-user">${select(
        "role",
        "Роль",
        [
          ["employee", "Сотрудник"],
          ["underwriter", "Андеррайтер"],
          ["actuary", "Актуарий"],
          ["admin", "Администратор"],
        ],
        u.role,
      )}<label class="check"><input type="checkbox" name="active" ${u.active ? "checked" : ""}>Учётная запись активна</label><button type="submit" class="primary">Сохранить</button></form>`,
    );
    bindForm("#edit-user", async (d) => {
      await api(`/admin/employees/${u.id}`, {
        method: "PATCH",
        body: JSON.stringify({ role: d.role, active: d.active === "on" }),
      });
      $("#modal").close();
      await adminEmployees();
    });
  });
}
async function adminLosses() {
  const rows = await api("/admin/losses");
  $("#admin-content").innerHTML =
    `<section class="panel"><div class="panel-head"><h3>Страховые случаи по годам</h3><button class="primary" id="add-loss">＋ Добавить данные</button></div><div class="table-wrap"><table><thead><tr><th>ПРОДУКТ / ГОД</th><th>СЛУЧАИ</th><th>ВЫПЛАТЫ</th><th>ПРЕМИИ</th><th>УБЫТОЧНОСТЬ</th><th>ЧАСТОТА</th></tr></thead><tbody>${rows.map((r) => `<tr><td>${esc(r.product_code)} · ${r.year}</td><td>${r.claims}</td><td>${money(r.payments)}</td><td>${money(r.premiums)}</td><td>${r.loss_ratio === null ? "—" : money(Number(r.loss_ratio) * 100) + "%"}</td><td>${r.frequency === null ? "—" : money(Number(r.frequency) * 100) + "%"}</td></tr>`).join("")}</tbody></table></div></section>${state.user.role === "admin" ? `<section class="panel"><h3>Импорт убытков</h3><p class="form-hint">Столбцы: product_code, name, year, claims, payments. Необязательно: premiums, contracts.</p><form id="import-form"><input name="file" type="file" accept=".csv,.xlsx" required><button type="submit" class="secondary">Предпросмотр</button></form><div id="import-preview"></div></section>` : `<section class="panel"><h3>Утверждение калибровки</h3><p class="form-hint">Три полных года, взвешенная убыточность. Поправка = убыточность / целевая убыточность − 1, ограничена ±20% и границей шаблона. Изменение исходных убытков отменяет применение старой калибровки.</p><form id="calibration-form"><div class="form-grid">${select("product_code", "Продукт", productOptions())}${field("target_loss_ratio", "Целевая убыточность (0–1)", "0.6", "number", 'min="0.01" max="1" step="0.01" required')}</div><label>Обоснование утверждения<textarea name="rationale" required minlength="10"></textarea></label><button type="submit" class="primary">Утвердить как актуарий</button></form></section>`}`;
  $("#add-loss").onclick = () => {
    modal(
      `<h2>Страховые случаи</h2><form id="loss-form"><div class="form-grid">${select("product_code", "Продукт", productOptions())}${field("year", "Завершённый год", new Date().getFullYear() - 1, "number", 'required min="1990"')}${field("claims", "Количество случаев", 0, "number", 'required min="0"')}${field("payments", "Сумма выплат, UZS", 0, "number", 'required min="0" step="0.01"')}${field("premiums", "Премии, UZS", "", "number", 'min="0" step="0.01"')}${field("contracts", "Количество договоров", "", "number", 'min="0"')}</div><button type="submit" class="primary">Сохранить</button></form>`,
    );
    bindForm("#loss-form", async (d) => {
      d.year = Number(d.year);
      d.claims = Number(d.claims);
      if (!d.premiums) delete d.premiums;
      if (d.contracts === "") delete d.contracts;
      else d.contracts = Number(d.contracts);
      await post("/admin/losses", d);
      $("#modal").close();
      await adminLosses();
    });
  };
  if ($("#import-form")) bindImport("losses");
  if ($("#calibration-form"))
    bindForm("#calibration-form", async (d) => {
      d.target_loss_ratio = Number(d.target_loss_ratio);
      const result = await post("/admin/calibrations", d);
      toast(
        `Калибровка утверждена. Поправка: ${Number(result.adjustment) * 100}%`,
      );
    });
}
async function adminTemplates() {
  const rows = await api("/templates");
  $("#admin-content").innerHTML =
    `<section class="panel"><div class="panel-head"><h3>Шаблоны страховых классов</h3><button class="primary" id="new-template">＋ Новый шаблон</button></div>${rows.map((r) => `<div class="file-card"><h3>${esc(r.name)} <small>${esc(r.class_code)}</small></h3><span class="badge ${r.approved_by ? "green" : "amber"}">${r.approved_by ? "Утверждён актуарием" : "Экспертный, не утверждён"}</span>${jsonDetails(r)}<div class="actions"><button class="secondary" data-edit-template="${r.id}">Новая версия</button>${state.user.role === "actuary" && !r.approved_by ? `<button class="primary" data-approve-template="${r.id}">Утвердить</button>` : ""}</div></div>`).join("")}</section>`;
  const edit = (r) => {
    const d = { ...r };
    delete d.id;
    delete d.approved_by;
    modal(
      `<h2>Версия шаблона</h2><p class="form-hint">Пороговые значения, веса, поправки, доли рисков, метрики и оговорки. Новая версия требует нового утверждения.</p><form id="template-form"><label>Настройки JSON<textarea name="data" rows="18" required>${esc(JSON.stringify(d, null, 2))}</textarea></label><button type="submit" class="primary">Сохранить версию</button></form>`,
    );
    bindForm("#template-form", async (values) => {
      await post("/admin/templates", JSON.parse(values.data));
      $("#modal").close();
      state.templates = await api("/templates");
      await adminTemplates();
    });
  };
  $("#new-template").onclick = () =>
    edit({
      class_code: "new-class",
      name: "Новый класс",
      feature_weights: {},
      moderate_threshold: 20,
      high_threshold: 50,
      multipliers: { low: "1", moderate: "1.15", high: "1.35" },
      clauses: [],
      risk_shares: {},
      indicator_metrics: [],
      max_adjustment: "0.2",
    });
  action("[data-edit-template]", (el) =>
    edit(rows.find((r) => r.id === el.dataset.editTemplate)),
  );
  action("[data-approve-template]", async (el) => {
    await post(`/admin/templates/${el.dataset.approveTemplate}/approve`);
    await adminTemplates();
  });
}
async function adminIndicators() {
  const data = await api("/sources");
  $("#admin-content").innerHTML =
    `<section class="panel"><h3>Загрузка показателя из проверенного источника</h3><p class="form-hint">Система не обращается по введённой ссылке. Значение загружает сотрудник; ссылка и дата сохраняются в акте. Поправки без подписи актуария помечаются как экспертные.</p><form id="indicator-form"><div class="form-grid">${select(
      "channel",
      "Канал",
      data.channels.map((c) => [c.code, c.data.domain]),
    )}${field("metric", "Код показателя", "regional_risk", "text", "required")}${field("region", "Регион (all = вся страна)", "all", "text", "required")}${field("class_code", "Класс (all = все)", "all", "text", "required")}${field("object_type", "Тип объекта (all = все)", "all", "text", "required")}${field("period", "Период", String(new Date().getFullYear()), "text", "required")}${field("value", "Значение", 0, "number", 'required min="0" step="any"')}${field("unit", "Единица", "index", "text", "required")}${field("source_url", "Ссылка на источник", "", "url", "required")}${field("observation_date", "Дата данных", today(), "date", "required")}${field("stale_days", "Срок актуальности, дней", 365, "number", 'required min="1"')}${field("rate_adjustment", "Поправка (0.1 = +10%)", 0, "number", 'min="-0.5" max="0.5" step="0.01"')}${field("annual_market_rate", "Рыночная годовая ставка, %", "", "number", 'min="0" max="100" step="0.000001"')}</div><button type="submit" class="primary">Сохранить показатель</button></form></section><section class="panel"><h3>История версий</h3><button id="indicator-history" class="secondary">Показать историю</button><div id="history-output"></div></section>`;
  bindForm("#indicator-form", async (d) => {
    const channel = d.channel;
    delete d.channel;
    if (!d.annual_market_rate) delete d.annual_market_rate;
    d.stale_days = Number(d.stale_days);
    await post(`/admin/sources/${channel}/indicators`, d);
    toast("Новая версия показателя сохранена");
  });
  action("#indicator-history", async () => {
    $("#history-output").innerHTML = jsonDetails(
      await api("/admin/indicators/history"),
      "Все версии",
    );
  });
}
async function adminAudit() {
  const rows = await api("/admin/audit");
  $("#admin-content").innerHTML =
    `<section class="panel"><h3>Журнал действий</h3><p class="muted small">Последние 200 событий. Правки сохраняют исходные и новые значения.</p><div class="table-wrap"><table><thead><tr><th>ВРЕМЯ</th><th>ДЕЙСТВИЕ</th><th>СОТРУДНИК / ОБЪЕКТ</th><th>ДЕТАЛИ</th></tr></thead><tbody>${rows.map((r) => `<tr><td>${esc(r.created_at)}</td><td>${esc(r.action)}</td><td>${esc(r.user_id || "Система")}<small>${esc(r.entity_id)}</small></td><td>${jsonDetails(r.data)}</td></tr>`).join("")}</tbody></table></div></section>`;
}

(async () => {
  try {
    await enter(await api("/auth/me"));
  } catch {
    const telegram = window.Telegram?.WebApp;
    telegram?.ready();
    if (telegram?.initData) {
      try {
        await enter(
          await post("/auth/telegram", { init_data: telegram.initData }),
        );
      } catch (err) {
        toast(err.message, true);
      }
    }
  }
})();
