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
    : new Intl.NumberFormat(
        state.locale === "uz"
          ? "uz-UZ"
          : state.locale === "en"
            ? "en-US"
            : "ru-RU",
        { maximumFractionDigits: 2 },
      ).format(Number(v));
const dateText = (v) => (v ? new Date(v).toLocaleDateString("ru-RU") : "—");
const today = () => new Date().toLocaleDateString("en-CA");
const state = {
  user: null,
  codexPilot: false,
  csrf: "",
  page: "surveys",
  products: [],
  templates: [],
  regions: [],
  references: [],
  survey: null,
  locale: ["ru", "uz", "en"].includes(localStorage.getItem("surveyor-language"))
    ? localStorage.getItem("surveyor-language")
    : "ru",
};
const translations = {
  ru: {
    surveys: "Осмотры",
    calculator: "Калькулятор",
    policy: "Тарифы и РНП",
    codex: "ИИ",
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
    policy: "Tariflar va RNP",
    codex: "AI",
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
    policy: "Tariffs and reserves",
    codex: "AI",
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
  official_file: "Открытый файл",
  official_api: "Официальный API",
  manual_only: "Только загрузка сотрудником",
  review_required: "Нужна проверка доступа",
  contract_required: "Нужен договор",
  collected: "Данные обновлены",
  cached: "Используются сохранённые данные",
  disabled: "Канал отключён",
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
  base_rate: "Базовая ставка, %",
  minimum_rate: "Минимальная ставка, %",
  recommended_rate: "Рекомендуемая ставка, %",
  premium: "Премия, UZS",
  risk_level: "Уровень риска",
  regional_adjustment: "Поправка региона",
  loss_adjustment: "Поправка убытков",
  formula: "Формула",
  warnings: "Предупреждения",
  contradiction: "Противоречие",
  evidence: "Сведения из источника",
  missing: "Недостающие сведения",
  risk: "Риск",
});
const regionName = (v) =>
  state.regions.find((r) => r.code === v)?.[state.locale] || v;
const named = (v) => window.SurveyorI18n.text(names[v] || v || "—");
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
  if (path.startsWith("/ai-pilot") && window.Telegram?.WebApp?.initData) {
    headers["X-Telegram-Init-Data"] = window.Telegram.WebApp.initData;
  }
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
      await handler(Object.fromEntries(new FormData(form)), form, e);
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
$("#login-locale").value = state.locale;
$("#login-locale").onchange = $("#locale").onchange = async (e) => {
  state.locale = e.target.value;
  window.SurveyorI18n.setLocale(state.locale);
  $("#locale").value = state.locale;
  $("#login-locale").value = state.locale;
  if (!state.user) return;
  if (state.user.must_change_password) return changePassword();
  renderNav();
  await navigate(state.page);
};

function renderNav() {
  const items = [
    ["surveys", "▧"],
    ["calculator", "⌗"],
    ["policy", "▤"],
    ["sources", "◎"],
  ];
  if (["admin", "actuary"].includes(state.user.role))
    items.push(["admin", "⚙"]);
  if (state.codexPilot) items.push(["codex", "✦"]);
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
  state.codexPilot = false;
  state.codexDocuments = false;
  if (state.user.role === "admin" && !state.user.must_change_password) {
    state.codexPilot = await api("/ai-pilot")
      .then((info) => {
        state.codexDocuments = info.documents_enabled;
        return true;
      })
      .catch(() => false);
  }
  $("#login-view").hidden = true;
  $("#workspace").hidden = false;
  $("#demo-banner").hidden = data.data_mode === "real";
  renderNav();
  if (state.user.must_change_password) {
    return changePassword();
  }
  state.regions = await api("/regions");
  state.products = await api("/products");
  state.templates = await api("/templates");
  await navigate("surveys");
}
async function navigate(page) {
  state.page = page;
  $("#demo-banner").textContent =
    page === "codex" && state.codexDocuments
      ? "Личный анализ документов. Учебные тарифы не утверждены страховщиком."
      : "Учебная среда · Используйте только синтетические данные. Демонстрационные тарифы не утверждены страховщиком.";
  renderNav();
  $("#breadcrumb").textContent = t(page);
  $("#content").innerHTML = '<div class="loading">Загрузка…</div>';
  try {
    await {
      surveys: dashboard,
      calculator: calculator,
      policy: window.SurveyorPolicy.page,
      codex: window.SurveyorCodexPilot.page,
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
  state.references = (await api("/sources")).references;
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
      ["assistant", "Помощник"],
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
  if (step === "assistant")
    window.SurveyorAssistant.page().catch((error) =>
      toast(error.message, true),
    );
  if (step === "review") renderReview();
  if (step === "report") renderReportList();
}
function renderFiles() {
  const s = state.survey;
  $("#survey-body").innerHTML =
    `<div class="two-col"><section class="panel"><div class="panel-head"><h3>Материалы осмотра</h3><span class="muted small">${s.documents.length} / 20 файлов</span></div>${s.owner_id === state.user.id ? `<form id="upload-form"><div class="upload-zone"><span class="empty-symbol">↑</span><strong>Добавьте фото, договор или запрос филиала</strong><p class="muted small">PDF, Word, Excel, TXT, CSV, JPG, PNG, WEBP<br>До 15 МБ на файл · PDF до 50 страниц</p><input type="file" name="file" multiple required accept=".pdf,.docx,.xlsx,.txt,.csv,.jpg,.jpeg,.png,.webp"></div><button type="submit" class="secondary">Загрузить выбранные файлы</button></form>` : ""}<div class="notice">Проверьте документы вручную. Если доступен ИИ, его предложения требуют вашей проверки.</div>${s.documents
      .map(
        (d) =>
          `<div class="file-card"><h4><a href="/api/documents/${d.id}/download">${esc(d.filename)} ↗</a></h4>${badge(d.extracted.mode)}${s.owner_id === state.user.id && state.codexDocuments ? `<button type="button" class="secondary" data-ai-document="${d.id}">ИИ · проверить документ</button>` : ""}${s.owner_id === state.user.id ? `<button type="button" class="text-button" data-review-document="${d.id}">Проверить / исправить поля</button>` : ""}<p class="small muted">${esc(d.extracted.notice)}</p><div>${Object.entries(
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
  action("[data-review-document]", (el) =>
    reviewDocument(s.documents.find((d) => d.id === el.dataset.reviewDocument)),
  );
  action("[data-ai-document]", (el) =>
    window.SurveyorInspectionAI.open(
      s.documents.find((d) => d.id === el.dataset.aiDocument),
    ),
  );
  $("#to-review").onclick = () => renderSurvey("review");
}
function reviewDocument(doc) {
  const keys = [
    "insured_sum",
    "object_value",
    "declared_rate",
    "declared_premium",
    "term_days",
    "object_description",
    "insured_organization",
    "insurer_organization",
    "contract_start",
    "contract_end",
  ];
  const kinds = [
    ["photo", "Фото объекта"],
    ["contract", "Договор"],
    ["branch_request", "Запрос филиала"],
    ["report", "Отчёт"],
    ["document", "Документ"],
  ];
  modal(
    `<h2>${esc(doc.filename)}</h2><p>Исходное распознавание сохраняется. Правки будут отмечены в акте.</p><form id="document-review">${select("kind", "Вид документа", kinds, doc.extracted.kind)}<div class="form-grid">${keys.map((k) => field(k, named(k), doc.extracted.fields[k]?.value || "", k.startsWith("contract_") ? "date" : "text")).join("")}</div><label>Причина / результат проверки<textarea name="reason" required minlength="5"></textarea></label><button class="primary" type="submit">Сохранить проверку</button></form>`,
  );
  bindForm("#document-review", async (d) => {
    const fields = Object.fromEntries(
      keys
        .filter(
          (k) => (d[k] || null) !== (doc.extracted.fields[k]?.value || null),
        )
        .map((k) => [k, d[k] || null]),
    );
    await api(`/documents/${doc.id}/review`, {
      method: "PUT",
      body: JSON.stringify({
        revision: state.survey.revision,
        kind: d.kind,
        fields,
        reason: d.reason,
      }),
    });
    $("#modal").close();
    await openSurvey(state.survey.id);
  });
}
function productOptions() {
  return state.products.map((p) => [
    p.code,
    `${p.code} · ${p.name} (${named(p.rate_type)})`,
  ]);
}
function basicFields(d = {}) {
  return `${select("product_code", "Продукт", productOptions(), d.product_code || state.products[0]?.code)}${select("region", "Регион", [...state.regions.filter((r) => r.code !== "all").map((r) => [r.code, r[state.locale]]), ...(d.region && !state.regions.some((r) => r.code === d.region) ? [[d.region, d.region]] : [])], d.region || "1726")}${field("insured_sum", "Страховая сумма, UZS", d.insured_sum || "", "number", 'required min="0.01" step="0.01"')}${field("object_value", "Стоимость объекта, UZS", d.object_value || "", "number", 'required min="0.01" step="0.01"')}${field("term_days", "Срок страхования, дней", d.term_days || 365, "number", 'required min="1" max="36500"')}${field("tariff_date", "Дата применения тарифа", d.tariff_date || today(), "date", "required")}${select(
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
    `<form id="review-form"><div class="two-col"><div><section class="panel"><div class="panel-head"><h3>Объект и условия</h3><span class="badge">Ручная проверка</span></div><div class="form-grid">${basicFields(inputs)}${field("contract_start", "Дата начала договора", inputs.contract_start || "", "date")}${field("contract_end", "Дата окончания договора", inputs.contract_end || "", "date")}<p class="form-hint span-2">При изменении дат срок считается без даты окончания. Если договор использует другой подсчёт, измените срок и укажите причину.</p><label class="span-2">Описание объекта<textarea name="object_description" maxlength="2000">${esc(inputs.object_description || "")}</textarea></label></div><p class="form-hint">Четыре основных поля: продукт, страховая сумма, стоимость, регион. Срок нужен для годовой ставки и сравнения с рынком.</p><h3>Признаки риска</h3><div class="feature-list" id="features"></div><h3>Нормы и материалы источников</h3><div class="feature-list">${state.references.map((r) => `<label><input type="checkbox" name="reference" value="${r.id}" ${(d.reference_ids || []).includes(r.id) ? "checked" : ""}>${esc(r.title)} · ${dateText(r.observation_date)}${r.stale ? " · Устарели" : ""}</label>`).join("") || `<p class="muted">Данные недоступны</p>`}</div></section><section class="panel"><h3>Сверка документов</h3><div class="form-grid">${field("declared_rate", "Тариф из запроса / договора, %", inputs.declared_rate || "", "number", 'min="0" max="100" step="0.000001"')}${field("declared_premium", "Премия из запроса / договора, UZS", inputs.declared_premium || "", "number", 'min="0" step="0.01"')}</div>${
      Object.keys(extracted).length
        ? `<p class="form-hint">Из документа: ${Object.entries(extracted)
            .map(([k, v]) => `${esc(named(k))} = ${esc(v)}`)
            .join(" · ")}</p>`
        : ""
    }<label>Причина исправлений распознанных значений<textarea name="override_reason" placeholder="Если исправили значение документа — объясните почему">${esc(d.override_reason || "")}</textarea></label></section><section class="panel"><h3>Оценка стоимости</h3><p class="form-hint">Сопоставимые предложения: то же изделие, цена и дата обязательны, не старше 6 месяцев. Медиана до ручных правок сохраняется рядом с оценкой. OLX — цены предложений. E-auksion — завершённые сделки с протоколом; стартовые цены исключаются.</p><div id="comparables"></div><button type="button" class="secondary" id="add-comparable">＋ Сопоставимое предложение</button><details><summary>Оборудование: цена покупки и износ</summary><div class="form-grid">${field("purchase_price", "Цена покупки, UZS", d.purchase_price || "", "number", 'min="0" step="0.01"')}${field("purchase_source", "Источник цены покупки", d.purchase_source || "")}${field("purchase_date", "Дата источника цены покупки", d.purchase_date || "", "date", `max="${today()}"`)}${field("depreciation_percent", "Износ, %", d.depreciation_percent || 0, "number", 'min="0" max="100" step="0.01"')}</div></details><details><summary>Крупный объект: отчёт оценщика + второй метод</summary><div class="form-grid">${field("appraiser_value", "Оценка, UZS", d.appraiser_value || "", "number", 'min="0"')}${field("appraiser_source", "Источник оценки", d.appraiser_source || "")}${field("appraiser_date", "Дата оценки", d.appraiser_date || "", "date")}${field("second_method_value", "Второй метод, UZS", d.second_method_value || "", "number", 'min="0"')}${field("second_method_source", "Источник второго метода", d.second_method_source || "")}${field("second_method_date", "Дата второго метода", d.second_method_date || "", "date")}</div></details></section>${borrowerFields(d.borrower, s.documents)}</div><aside><section class="panel"><span class="section-title">ПЕРЕД ФОРМИРОВАНИЕМ</span><h3>Проверьте исходные данные</h3><p class="muted small">Расчёт использует версию тарифа на выбранную дату. Все введённые сотрудником значения отмечаются в акте.</p>${select(
      "language",
      "Язык акта",
      [
        ["ru", "Русский"],
        ["uz", "O‘zbekcha"],
        ["en", "English"],
      ],
      d.language || state.locale,
    )}<p class="form-hint">Тексты источников и оговорок сохраняются на исходном языке.</p><label class="check"><input name="manual_review_confirmed" type="checkbox" required ${d.manual_review_confirmed ? "checked" : ""}>Я проверил(а) документы, суммы, сроки и фотографии.</label><button type="button" id="save-draft" class="secondary full">Сохранить черновик → помощник</button><button type="submit" class="primary full" ${s.owner_id !== state.user.id ? "disabled" : ""}>Сохранить и сформировать →</button><p class="form-error"></p></section><div class="notice">Страховой балл не является кредитным скорингом. Окончательное решение принимает андеррайтер.</div></aside></div></form>`;
  $("#review-form .two-col > div").insertAdjacentHTML(
    "beforeend",
    `<section class="panel"><details><summary>Учётная группа РНП (необязательно)</summary>${window.SurveyorPolicy.rnpFields(d.rnp_context || {})}</details></section>`,
  );
  window.SurveyorInspectionAI.bindTransfer();
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
  for (const key of ["contract_start", "contract_end"])
    $(`[name=${key}]`).onchange = () => {
      const start = $("[name=contract_start]").value;
      const end = $("[name=contract_end]").value;
      if (start && end) {
        const days = (Date.parse(end) - Date.parse(start)) / 86400000;
        if (days > 0) $("[name=term_days]").value = days;
      }
    };
  const toggleBorrower = () => {
    const enabled = $("[name=borrower_enabled]").checked;
    $("#borrower-fields").hidden = !enabled;
    $$("input,select,textarea", $("#borrower-fields")).forEach((el) => {
      el.disabled = !enabled;
      el.required = enabled && el.name !== "borrower_summary";
    });
  };
  $("[name=borrower_enabled]").onchange = toggleBorrower;
  toggleBorrower();
  $("[name=product_code]").onchange = renderFeatures;
  for (const c of d.comparables || []) addComparable(c);
  $("#add-comparable").onclick = () => addComparable();
  $("#save-draft").onclick = () => {
    const form = $("#review-form");
    form.dataset.draft = "true";
    form.noValidate = true;
    form.requestSubmit();
  };
  bindForm("#review-form", async (values, form) => {
    const draft = form.dataset.draft === "true";
    delete form.dataset.draft;
    form.noValidate = false;
    const body = surveyBody(values);
    body.rnp_context = window.SurveyorPolicy.readRnp(values);
    body.revision = s.revision;
    body.features = $$("input[name=feature]:checked", form).map((x) => x.value);
    body.reference_ids = [
      ...new Set([
        ...$$("input[name=reference]:checked", form).map((x) => x.value),
        ...(d.reference_ids || []).filter(
          (id) => !state.references.some((r) => r.id === id),
        ),
      ]),
    ];
    body.manual_review_confirmed = !draft;
    body.borrower = null;
    if ($("[name=borrower_enabled]", form).checked) {
      body.borrower = {};
      for (const key of [
        "organization_name",
        "bureau_name",
        "document_id",
        "report_date",
        "score",
        "score_scale",
        "summary",
      ])
        body.borrower[key] = values[`borrower_${key}`] || "";
    }
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
    if (draft) {
      await openSurvey(s.id, "assistant");
      return;
    }
    const report = await post(`/surveys/${s.id}/reports`);
    state.survey = await api(`/surveys/${s.id}`);
    renderSurvey("report");
    await showReport(report.id);
    toast("Акт сформирован");
  });
}
function borrowerFields(data, documents) {
  const d = data || {};
  return `<section class="panel"><h3>Заёмщик</h3><label class="check"><input name="borrower_enabled" type="checkbox" ${data ? "checked" : ""}>Добавить сведения из отчёта кредитного бюро</label><p class="form-hint">Только организация. Загрузите отчёт в этот осмотр и перенесите оценку вместе со шкалой бюро. Страховой тариф автоматически не меняется.</p><div id="borrower-fields"><div class="form-grid">${field("borrower_organization_name", "Организация-заёмщик", d.organization_name || "")}${field("borrower_bureau_name", "Кредитное бюро", d.bureau_name || "")}${select("borrower_document_id", "Загруженный отчёт бюро", [["", "Выберите файл"], ...documents.map((doc) => [doc.id, doc.filename])], d.document_id || "")}${field("borrower_report_date", "Дата отчёта бюро", d.report_date || "", "date", `max="${today()}"`)}${field("borrower_score", "Оценка бюро", d.score || "")}${field("borrower_score_scale", "Шкала оценки бюро", d.score_scale || "")}</div><label>Результат проверки сотрудником<textarea name="borrower_summary" maxlength="3000">${esc(d.summary || "")}</textarea></label></div></section>`;
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
    ["transaction_reference", "Подтверждение сделки / протокол", "text"],
  ]
    .map(
      ([key, label, type]) =>
        `<label>${label}<input data-key="${key}" type="${type}" value="${esc(c[key] || (key === "currency" ? "UZS" : ""))}" ${["label", "price", "date", "source", "currency"].includes(key) ? "required" : ""} ${type === "number" ? 'min="0.01" step="0.01"' : ""}></label>`,
    )
    .join("")}<label>Тип цены<select data-key="evidence_kind">${[
    ["asking_price", "Цена предложения"],
    ["completed_sale", "Завершённая сделка"],
    ["auction_start", "Стартовая цена торгов"],
  ]
    .map(
      ([key, label]) =>
        `<option value="${key}" ${key === (c.evidence_kind || "asking_price") ? "selected" : ""}>${label}</option>`,
    )
    .join(
      "",
    )}</select></label></div><label class="check"><input data-key="same_item" type="checkbox" ${c.same_item !== false ? "checked" : ""}>То же изделие / сопоставимый объект</label><button class="text-button danger-button" type="button">Удалить предложение</button>`;
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
    "contract_start",
    "contract_end",
    "object_type",
    "program",
    "object_description",
    "declared_rate",
    "declared_premium",
    "purchase_price",
    "purchase_source",
    "purchase_date",
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
    c = s.calculation;
  $("#report-view").innerHTML =
    `<div class="actions"><a class="secondary" data-report-export="docx" href="/api/reports/${id}/export/docx">↓ Word</a><a class="secondary" data-report-export="pdf" href="/api/reports/${id}/export/pdf">↓ PDF</a><button class="primary" id="send-telegram">Отправить себе в Telegram ↗</button></div><p class="report-note">Акт № ${id.slice(0, 8)} · ${dateText(report.created_at)} · Подлежит подтверждению андеррайтером · Не является кредитным скорингом</p>${calculationView(c)}<p>${esc(named(c.comparison))} · ${money(c.premium_discrepancy)} UZS</p><section class="panel" data-no-translate>${report.sections.map((block) => `<div class="report-section"><h3>${esc(block.title)}</h3>${block.lines.map((line) => `<p class="small">${esc(line)}</p>`).join("")}</div>`).join("")}</section><section class="panel"><h3>Решение андеррайтера</h3>${report.decisions.map((d) => `<div class="file-card">${badge(d.data.decision)}<p>${esc(d.data.comment)}</p><small>${dateText(d.created_at)} · ${esc(d.user_id)}</small></div>`).join("") || '<p class="muted small">Решение ещё не принято.</p>'}${
      state.user.role === "underwriter"
        ? `<form id="decision-form">${select("decision", "Решение", [
            ["changes_requested", "Нужны правки"],
            ["approved", "Утвердить"],
            ["rejected", "Отклонить"],
          ])}<label>Комментарий<textarea name="comment" required minlength="3"></textarea></label><button type="submit" class="primary">Зафиксировать решение</button></form>`
        : ""
    }</section>`;
  $$("[data-report-export]", $("#report-view")).forEach((link) => {
    link.onclick = async (event) => {
      const telegram = window.Telegram?.WebApp;
      if (!telegram?.initData) return;
      event.preventDefault();
      if (link.getAttribute("aria-busy") === "true") return;
      link.setAttribute("aria-busy", "true");
      try {
        const file = await post(
          `/reports/${id}/export/${link.dataset.reportExport}/download-link`,
        );
        if (telegram.isVersionAtLeast?.("8.0") && telegram.downloadFile) {
          telegram.downloadFile({ url: file.url, file_name: file.file_name });
        } else {
          // A fresh click preserves the user gesture needed by older clients.
          modal(
            `<h2>Загрузить файл</h2><button type="button" class="primary" id="open-report-file">Открыть файл</button>`,
          );
          $("#open-report-file").onclick = () => telegram.openLink(file.url);
        }
      } catch (error) {
        toast(error.message, true);
      } finally {
        link.removeAttribute("aria-busy");
      }
    };
  });
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
  const manager = ["admin", "actuary"].includes(state.user.role);
  $("#content").innerHTML =
    heading(
      t("sources"),
      "У каждого показателя — источник, период и история версий.",
    ) +
    `<section class="panel"><h3>Реестр каналов</h3><div class="table-wrap"><table><thead><tr><th>ИСТОЧНИК</th><th>ДОСТУП И СОСТОЯНИЕ</th><th>ОБНОВЛЕНИЕ</th><th></th></tr></thead><tbody>${data.channels.map((c) => `<tr><td><strong>${esc(c.data.domain)}</strong><small>${esc(c.data.note)}</small>${c.data.config ? `<small><a href="${esc(c.data.config.permission_url)}" target="_blank" rel="noopener">Основание доступа ↗</a></small>` : ""}</td><td><span class="badge ${c.enabled ? "green" : "amber"}">${esc(c.enabled ? "Подключён" : named(c.data.access))}</span>${c.error ? `<small class="form-error">${esc(c.error)}</small>` : ""}</td><td>${dateText(c.last_success)}</td><td><div class="actions">${manager && c.enabled ? `<button class="secondary" data-collect="${c.code}">Обновить</button>` : ""}${state.user.role === "admin" ? `<button class="text-button" data-source-settings="${c.code}">Настроить</button>` : ""}${manager ? `<button class="text-button" data-source-import="${c.code}">Загрузить файл</button>` : ""}</div></td></tr>`).join("")}</tbody></table></div></section>
    <section class="panel"><h3>Нормы и материалы источников</h3>${manager ? `<button id="add-reference" class="secondary">＋ Добавить материал</button>` : ""}${data.references.map((r) => `<div class="file-card" data-no-translate><h4>${esc(r.title)}</h4><a href="${esc(r.source_url)}" target="_blank" rel="noopener">${esc(r.source_url)}</a><p>${dateText(r.observation_date)} · ${r.stale ? esc(named("stale")) : ""}</p><details><summary>${esc(window.SurveyorI18n.text("Текст источника"))}</summary><p class="reference-text">${esc(r.text)}</p></details></div>`).join("")}</section><section class="panel"><h3>Сохранённые показатели</h3><label>Фильтр по показателю или региону<input id="source-filter" type="search"></label><div id="indicator-list"></div></section>`;
  if ($("#add-reference"))
    $("#add-reference").onclick = () => referenceModal(data.channels);
  const render = () => {
    const q = $("#source-filter").value.toLowerCase();
    const rows = data.indicators.filter((i) =>
      [
        i.metric,
        sourceMetricName(i.metric),
        i.region,
        regionName(i.region),
        i.channel,
        i.subject,
        i.class_code,
      ]
        .join(" ")
        .toLowerCase()
        .includes(q),
    );
    $("#indicator-list").innerHTML =
      rows
        .map(
          (i) =>
            `<div class="file-card"><strong>${esc(i.subject === "market" ? "" : i.subject || "")} ${esc(sourceMetricName(i.metric))} · ${money(i.value)} ${esc(i.unit)}</strong> ${i.stale ? '<span class="badge amber">Устарели</span>' : ""}<p class="small muted">${esc(regionName(i.region))} · ${esc(i.class_code)} · ${esc(i.period)} · <a href="${esc(i.source_url)}" target="_blank" rel="noopener noreferrer">Источник ↗</a> · ${dateText(i.observation_date)}</p><p class="small">${i.reference_only ? "Только справочно; тариф не меняет" : i.approved_by ? "Утверждён актуарием" : "Экспертный, не утверждён"}</p>${i.note ? `<p class="form-hint" data-no-translate>${esc(i.note)}</p>` : ""}${state.user.role === "actuary" && !i.approved_by && !i.reference_only ? `<button class="secondary" data-approve-indicator="${i.id}">Утвердить поправку</button>` : ""}</div>`,
        )
        .join("") || "<p>Данные недоступны</p>";
    action("[data-approve-indicator]", async (el) => {
      await post(`/admin/indicators/${el.dataset.approveIndicator}/approve`);
      await sourcesPage();
    });
  };
  render();
  $("#source-filter").oninput = render;
  action("[data-collect]", async (el) => {
    const r = await post(`/admin/sources/${el.dataset.collect}/collect`);
    toast(r.message || named(r.status), r.status === "error");
    await sourcesPage();
  });
  action("[data-source-settings]", (el) =>
    sourceSettings(
      data.channels.find((c) => c.code === el.dataset.sourceSettings),
    ),
  );
  action("[data-source-import]", (el) => sourceImport(el.dataset.sourceImport));
}
function sourceSettings(channel) {
  const c = channel.data.config || {};
  const columns = c.columns || {},
    constants = c.constants || {};
  const fields = [
    "metric",
    "region",
    "class_code",
    "object_type",
    "period",
    "value",
    "unit",
    "observation_date",
    "stale_days",
    "annual_market_rate",
  ];
  modal(
    `<h2>Настройки источника · ${esc(channel.data.domain)}</h2>${
      channel.code !== "cbu"
        ? `<form id="source-config"><div class="form-grid">${field("url", "Адрес открытого файла / таблицы", c.url || "", "url", "required")}${select(
            "format",
            "Формат",
            [
              ["json", "JSON"],
              ["csv", "CSV"],
              ["xlsx", "Excel"],
              ["html_table", "Таблица на странице"],
              ["siat", "SIAT: статистика"],
              ["document", "Документ / страница (отслеживание изменений)"],
              ["napp", "NAPP: официальный страховой рынок"],
              ["napp_reference", "NAPP: справочные таблицы"],
            ],
            c.format || "csv",
          )}${field("permission_url", "Ссылка на разрешение / условия доступа", c.permission_url || "", "url", "required")}${field("interval_hours", "Интервал обновления, часов", c.interval_hours || 24, "number", 'min="24" max="720" required')}${field("json_path", "Путь к списку в JSON (если вложен)", c.json_path || "")}${field("table_index", "Номер HTML-таблицы (с нуля)", c.table_index || 0, "number", 'min="0" max="30"')}</div><label>Основание автоматического доступа<textarea name="permission_note" required minlength="15">${esc(c.permission_note || "")}</textarea></label><h3>Документ / страница</h3><div class="form-grid">${field("reference_title", "Название материала", c.reference?.title || "")}${field("reference_date", "Дата публикации (если известна)", c.reference?.observation_date || "", "date")}</div><h3>Соответствие столбцов</h3><p class="form-hint">Укажите название столбца в файле или постоянное значение. SIAT сам определяет регион, период и единицы.</p><div class="table-wrap"><table><thead><tr><th>Поле</th><th>Столбец файла</th><th>Постоянное значение</th></tr></thead><tbody>${fields.map((k) => `<tr><td>${esc(named(k))}</td><td><input name="column_${k}" value="${esc(columns[k] || "")}"></td><td><input name="constant_${k}" value="${esc(constants[k] ?? "")}"></td></tr>`).join("")}</tbody></table></div><button type="submit" class="primary">Сохранить и включить</button></form>`
        : ""
    }<form id="source-toggle"><label>Причина изменения состояния<textarea name="reason" required minlength="10"></textarea></label><button type="submit" class="secondary">${channel.enabled ? "Отключить канал" : "Включить после проверки"}</button></form>`,
  );
  if ($("#source-config"))
    bindForm("#source-config", async (d) => {
      const body = {
        url: d.url,
        format: d.format,
        permission_url: d.permission_url,
        permission_note: d.permission_note,
        interval_hours: Number(d.interval_hours),
        json_path: d.json_path,
        table_index: Number(d.table_index),
        columns: {},
        constants: {},
      };
      if (d.format === "document")
        body.reference = {
          title: d.reference_title,
          observation_date: d.reference_date || null,
        };
      for (const k of fields) {
        if (d[`column_${k}`]) body.columns[k] = d[`column_${k}`];
        else if (d[`constant_${k}`] !== "")
          body.constants[k] = d[`constant_${k}`];
      }
      await api(`/admin/sources/${channel.code}/config`, {
        method: "PUT",
        body: JSON.stringify(body),
      });
      $("#modal").close();
      await sourcesPage();
    });
  bindForm("#source-toggle", async (d) => {
    await api(`/admin/sources/${channel.code}`, {
      method: "PATCH",
      body: JSON.stringify({ enabled: !channel.enabled, reason: d.reason }),
    });
    $("#modal").close();
    await sourcesPage();
  });
}
function sourceImport(code) {
  modal(
    `<h2>Загрузка показателей</h2><p>Загрузите CSV или Excel. Сначала проверьте строки, затем подтвердите сохранение.</p><a href="/api/admin/sources/import-template">Скачать шаблон CSV ↓</a><form id="source-import"><input type="file" name="file" accept=".csv,.xlsx" required><button type="submit" class="secondary">Предпросмотр</button></form><div id="source-preview"></div>`,
  );
  bindForm("#source-import", async (_, form) => {
    const batch = await api(`/admin/sources/${code}/imports/preview`, {
      method: "POST",
      body: new FormData(form),
    });
    $("#source-preview").innerHTML =
      `<div class="table-wrap"><table><thead><tr><th>Строка</th><th>Показатель</th><th>Период</th><th>Значение / ошибка</th></tr></thead><tbody>${batch.rows.map((r) => `<tr><td>${r.row}</td><td>${esc(r.data?.metric || "—")}</td><td>${esc(r.data?.period || "—")}</td><td>${esc(r.error || r.data?.value)}</td></tr>`).join("")}</tbody></table></div><button id="source-confirm" class="primary" ${batch.can_confirm ? "" : "disabled"}>Подтвердить сохранение</button>`;
    action("#source-confirm", async () => {
      await post(`/admin/source-imports/${batch.id}/confirm`);
      $("#modal").close();
      await sourcesPage();
    });
  });
}
function referenceModal(channels) {
  modal(
    `<h2>Материал источника</h2><form id="reference-form"><div class="form-grid">${select(
      "channel",
      "Канал",
      channels.map((c) => [c.code, c.data.domain]),
    )}${field("title", "Название материала", "", "text", "required")}${field("source_url", "Ссылка на источник", "", "url", "required")}${field("observation_date", "Дата публикации (если известна)", "", "date")}${select(
      "kind",
      "Вид материала",
      [
        ["law", "Нормативный акт"],
        ["seismic", "Сейсмика"],
        ["weather", "Погода"],
        ["auction", "Торги"],
        ["price", "Цены"],
        ["registry", "Реестр"],
        ["other", "Другое"],
      ],
    )}${field("region", "Регион (all = вся страна)", "all")}${field("class_code", "Класс (all = все)", "all")}${field("stale_days", "Срок актуальности, дней", 365, "number", 'required min="1" max="3650"')}</div><label>Прочитать текст из файла<input id="reference-file" type="file" accept=".pdf,.docx,.xlsx,.txt,.csv"></label><label>Текст источника<textarea name="text" rows="10" required maxlength="50000"></textarea></label><p>Сохранение изменённого текста создаёт новую версию. Старые акты сохраняют прежнюю.</p><button type="submit" class="primary">Сохранить материал</button></form>`,
  );
  $("#reference-file").onchange = async (e) => {
    try {
      const fd = new FormData();
      fd.append("file", e.target.files[0]);
      const r = await api("/admin/source-files/read", {
        method: "POST",
        body: fd,
      });
      $("#reference-form [name=text]").value = r.text;
      if (r.manual) toast("Фото и сканы требуют ручного ввода");
    } catch (err) {
      toast(err.message, true);
    }
  };
  bindForm("#reference-form", async (d) => {
    const channel = d.channel;
    delete d.channel;
    d.observation_date = d.observation_date || null;
    d.stale_days = Number(d.stale_days);
    await post(`/admin/sources/${channel}/references`, d);
    $("#modal").close();
    await sourcesPage();
  });
}
async function operationsPage() {
  const d = await api("/admin/operations");
  $("#admin-content").innerHTML =
    `<section class="panel"><h3>Состояние системы</h3><p>Режим: ${esc(d.data_mode)} · ИИ отключён</p><p>Последний запуск фоновых задач: ${dateText(d.worker[0]?.date)}</p><h3>Резервные копии</h3>${d.backups.map((b) => `<p>${esc(b.name)}</p>`).join("") || "<p>Резервных копий пока нет</p>"}<h3>Ошибки источников и резервного копирования</h3>${d.alerts.map((a) => `<div class="notice">${esc(a.channel)} · ${dateText(a.date)}<p>${esc(a.message)}</p></div>`).join("") || "<p>Ошибок нет</p>"}</section>`;
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
          ["operations", "Состояние системы"],
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
    operations: operationsPage,
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
async function productModal(p = {}) {
  await window.SurveyorPolicy.prepare();
  modal(
    `<h2>${p.id ? "Новая версия тарифа" : "Добавить продукт"}</h2><form id="product-form"><div class="form-grid">${field("code", "Код", p.code || "", "text", "required")}${field("name", "Название", p.name || "", "text", "required")}${field("class_code", "Класс", p.class_code || "property", "text", "required")}${field("effective_from", "Дата начала действия", p.id ? today() : p.effective_from || (p.policy_code ? "" : today()), "date", "required")}${field("rate", "Ставка, %", p.rate || "", "number", 'required min="0" max="100" step="0.000001"')}${field("min_rate", "Минимум, %", p.min_rate || "", "number", 'required min="0" max="100" step="0.000001"')}${select(
      "rate_type",
      "Тип ставки",
      [
        ["", "Выберите базу по условиям"],
        ["annual", "Годовая"],
        ["fixed", "Фиксированная"],
        ["program", "По программе"],
        ["normative", "По нормативному акту"],
      ],
      p.rate_type ?? "annual",
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
    )}${field("normative_source", "Ссылка на нормативный акт", p.normative_source || "", "url")}<div class="span-2"><h3>Ставки программ</h3>${dictionaryEditor("program-rates", p.program_rates, "Программа", "Ставка, %")}</div></div><p class="form-hint">Ставки хранятся в процентах: 0.5 означает 0,5%. Изменение создаёт новую версию.</p><button type="submit" class="primary">Сохранить версию</button></form>`,
  );
  $("#product-form button[type=submit]").insertAdjacentHTML(
    "beforebegin",
    window.SurveyorPolicy.productFields(p),
  );
  window.SurveyorPolicy.bindProduct(p);
  bindDictionaries();
  bindForm("#product-form", async (d, form) => {
    window.SurveyorPolicy.readProduct(d, form);
    d.program_rates = readDictionary("program-rates");
    if (!d.normative_basis) delete d.normative_basis;
    if (!d.normative_source) delete d.normative_source;
    await post("/admin/products", d);
    $("#modal").close();
    state.products = await api("/products");
    if (state.page === "policy") await window.SurveyorPolicy.page();
    else await adminProducts();
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
function dictionaryEditor(id, values, keyLabel, valueLabel) {
  return `<div id="${id}" class="dictionary-editor" data-key-label="${esc(keyLabel)}" data-value-label="${esc(valueLabel)}"><div class="dictionary-rows">${Object.entries(
    values || {},
  )
    .map(([k, v]) => dictionaryRow(k, v, keyLabel, valueLabel))
    .join(
      "",
    )}</div><button type="button" class="secondary" data-add-dictionary="${id}">＋ Добавить строку</button></div>`;
}
function dictionaryRow(key, value, keyLabel, valueLabel) {
  return `<div class="dictionary-row form-grid"><label>${esc(keyLabel)}<input data-dict-key required value="${esc(key)}"></label><label>${esc(valueLabel)}<input data-dict-value type="number" min="0" max="100" step="any" required value="${esc(value)}"></label><button type="button" class="text-button" data-remove-row>Удалить строку</button></div>`;
}
function bindDictionaries() {
  action("[data-add-dictionary]", (el) => {
    const root = document.getElementById(el.dataset.addDictionary);
    $(".dictionary-rows", root).insertAdjacentHTML(
      "beforeend",
      dictionaryRow("", "", root.dataset.keyLabel, root.dataset.valueLabel),
    );
    bindRemoveRows();
  });
  bindRemoveRows();
}
function bindRemoveRows() {
  $$("[data-remove-row]").forEach(
    (el) => (el.onclick = () => el.closest(".dictionary-row").remove()),
  );
}
function readDictionary(id) {
  const out = {};
  for (const row of $$(".dictionary-row", document.getElementById(id))) {
    const key = $("[data-dict-key]", row).value.trim();
    if (Object.hasOwn(out, key))
      throw new Error("Названия строк должны быть уникальны");
    out[key] = $("[data-dict-value]", row).value;
  }
  return out;
}
async function editTemplate(r) {
  const catalogue = await api("/admin/source-coverage");
  const d = { ...r };
  delete d.id;
  delete d.approved_by;
  modal(
    `<h2>Версия шаблона</h2><p>Новая версия требует нового утверждения актуарием.</p><form id="template-form"><div class="form-grid">${field("class_code", "Класс", d.class_code || "", "text", "required")}${field("name", "Название", d.name || "", "text", "required")}${field("moderate_threshold", "Порог умеренного риска", d.moderate_threshold || 20, "number", 'required min="1" max="100"')}${field("high_threshold", "Порог высокого риска", d.high_threshold || 50, "number", 'required min="1" max="100"')}${["low", "moderate", "high"].map((k) => field(`multiplier_${k}`, `Множитель: ${named(k)}`, d.multipliers?.[k] || 1, "number", 'required min="0.5" max="3" step="0.01"')).join("")}${field("max_adjustment", "Граница поправки (0.2 = 20%)", d.max_adjustment || "0.2", "number", 'required min="0" max="0.5" step="0.01"')}</div><h3>Признаки и веса риска</h3>${dictionaryEditor("feature-weights", d.feature_weights, "Признак", "Вес (0–100)")}<h3>Доли рисков, %</h3>${dictionaryEditor("risk-shares", d.risk_shares, "Риск", "Доля, %")}<h3>Правила оценки стоимости</h3><div class="form-grid">${field("valuation_outlier_low", "Нижняя граница медианы", d.valuation_outlier_low ?? "0.5", "number", 'required min="0.01" max="1" step="0.01"')}${field("valuation_outlier_high", "Верхняя граница медианы", d.valuation_outlier_high ?? "1.5", "number", 'required min="1" max="10" step="0.01"')}${field("valuation_tolerance", "Допустимое отклонение (0.15 = 15%)", d.valuation_tolerance ?? "0.15", "number", 'required min="0" max="1" step="0.01"')}${field("large_object_threshold", "Порог крупного объекта, UZS", d.large_object_threshold || "", "number", 'min="0.01" step="0.01"')}</div><label>Показатели с готовой поправкой (по одному на строке)<textarea name="indicator_metrics">${esc((d.indicator_metrics || []).join("\n"))}</textarea></label><h3>Поправки из статистики</h3><p class="form-hint">Поправка = (значение / базовое значение − 1) × чувствительность. Применяется только к выбранным видам объектов, в пределах границы.</p><datalist id="available-metrics">${[...new Set(catalogue.metrics.filter((m) => m.fresh > 0 && !m.reference_only).map((m) => m.metric))].map((metric) => `<option value="${esc(metric)}"></option>`).join("")}</datalist><div id="indicator-rules"></div><button type="button" id="add-indicator-rule" class="secondary">＋ Правило показателя</button><h3>Оговорки</h3>${["ru", "uz", "en"].map((lang) => `<label>${lang.toUpperCase()}<textarea name="clauses_${lang}" rows="4">${esc((lang === "ru" ? d.clauses || [] : d.clauses_translations?.[lang] || []).join("\n"))}</textarea></label>`).join("")}<p class="form-hint">Каждая оговорка — отдельная строка. Тексты утверждает страховщик.</p><button type="submit" class="primary">Сохранить версию</button></form>`,
  );
  bindDictionaries();
  const addRule = (metric = "", rule = {}) => {
    const el = document.createElement("div");
    el.className = "indicator-rule panel";
    el.innerHTML = `<div class="form-grid">${field("metric", "Код показателя", metric, "text", 'required list="available-metrics"')}${field("baseline", "Базовое значение", rule.baseline || "", "number", 'required min="0.000001" step="any"')}${field("sensitivity", "Чувствительность (−1…1)", rule.sensitivity || "0", "number", 'required min="-1" max="1" step="0.01"')}${field("max_adjustment", "Граница поправки (0.2 = 20%)", rule.max_adjustment || "0.1", "number", 'required min="0" max="0.5" step="0.01"')}</div><div class="feature-list">${[
      ["vehicle", "Автомобиль"],
      ["equipment", "Оборудование"],
      ["housing", "Жильё / техника"],
      ["large", "Крупный объект"],
      ["other", "Другое"],
    ]
      .map(
        ([k, l]) =>
          `<label><input type="checkbox" data-object-type="${k}" ${(rule.object_types || []).includes(k) ? "checked" : ""}>${l}</label>`,
      )
      .join(
        "",
      )}</div><button type="button" class="text-button">Удалить правило</button>`;
    $("button", el).onclick = () => el.remove();
    $("#indicator-rules").append(el);
  };
  Object.entries(d.indicator_rules || {}).forEach(([metric, rule]) =>
    addRule(metric, rule),
  );
  $("#add-indicator-rule").onclick = () => addRule();
  bindForm("#template-form", async (values) => {
    const body = {
      class_code: values.class_code,
      name: values.name,
      moderate_threshold: Number(values.moderate_threshold),
      high_threshold: Number(values.high_threshold),
      multipliers: Object.fromEntries(
        ["low", "moderate", "high"].map((k) => [k, values[`multiplier_${k}`]]),
      ),
      max_adjustment: values.max_adjustment,
      feature_weights: Object.fromEntries(
        Object.entries(readDictionary("feature-weights")).map(([k, v]) => [
          k,
          Number(v),
        ]),
      ),
      risk_shares: readDictionary("risk-shares"),
      valuation_outlier_low: values.valuation_outlier_low,
      valuation_outlier_high: values.valuation_outlier_high,
      valuation_tolerance: values.valuation_tolerance,
      large_object_threshold: values.large_object_threshold || null,
      indicator_metrics: values.indicator_metrics
        .split("\n")
        .map((x) => x.trim())
        .filter(Boolean),
      indicator_rules: {},
      clauses: values.clauses_ru
        .split("\n")
        .map((x) => x.trim())
        .filter(Boolean),
      clauses_translations: {},
    };
    for (const lang of ["uz", "en"])
      if (values[`clauses_${lang}`].trim())
        body.clauses_translations[lang] = values[`clauses_${lang}`]
          .split("\n")
          .map((x) => x.trim())
          .filter(Boolean);
    for (const el of $$(".indicator-rule")) {
      const key = $("[name=metric]", el).value;
      if (Object.hasOwn(body.indicator_rules, key))
        throw new Error("Названия строк должны быть уникальны");
      body.indicator_rules[key] = {
        baseline: $("[name=baseline]", el).value,
        sensitivity: $("[name=sensitivity]", el).value,
        max_adjustment: $("[name=max_adjustment]", el).value,
        object_types: $$("[data-object-type]:checked", el).map(
          (x) => x.dataset.objectType,
        ),
      };
    }
    await post("/admin/templates", body);
    $("#modal").close();
    state.templates = await api("/templates");
    await adminTemplates();
  });
}

async function adminTemplates() {
  const [rows, coverage] = await Promise.all([
    api("/templates"),
    api("/admin/source-coverage"),
  ]);
  $("#admin-content").innerHTML =
    `<section class="panel"><div class="panel-head"><h3>Шаблоны страховых классов</h3><button class="primary" id="new-template">＋ Новый шаблон</button></div>${rows.map((r) => `<div class="file-card"><h3>${esc(r.name)} <small>${esc(r.class_code)}</small></h3><span class="badge ${r.approved_by ? "green" : "amber"}">${r.approved_by ? "Утверждён актуарием" : "Экспертный, не утверждён"}</span>${jsonDetails(r)}<div class="actions"><button class="secondary" data-edit-template="${r.id}">Новая версия</button>${state.user.role === "actuary" && !r.approved_by ? `<button class="primary" data-approve-template="${r.id}">Утвердить</button>` : ""}</div></div>`).join("")}</section>`;
  $("#admin-content").insertAdjacentHTML(
    "beforeend",
    sourceCoveragePanel(coverage),
  );
  const edit = (row) =>
    editTemplate(row).catch((err) => toast(err.message, true));
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
  $("#admin-content").insertAdjacentHTML("afterbegin", marketQuoteForm());
  bindMarketQuote();
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
  await window.SurveyorI18n.ready;
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
