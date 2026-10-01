"use strict";
// Translate known interface copy only. Inputs, source excerpts and JSON evidence stay verbatim.
window.SurveyorI18n = (() => {
  let language = ["ru", "uz", "en"].includes(
    localStorage.getItem("surveyor-language"),
  )
    ? localStorage.getItem("surveyor-language")
    : "ru";
  let catalog = {};
  const records = new WeakMap();
  const normalize = (s) => s.replace(/\s+/g, " ").trim();
  const patterns = [
    [
      /^(.+) ставка · (\d+) дней · (.+)$/,
      "$1 stavka · $2 kun · $3",
      "$1 rate · $2 days · $3",
    ],
    [
      /^Годовой эквивалент рекомендации: (.+)%. Рыночная ставка всегда сравнивается в годовом выражении\.$/,
      "Tavsiyaning yillik ekvivalenti: $1%. Bozor stavkasi yillik asosda solishtiriladi.",
      "Annual equivalent of the recommendation: $1%. Market rates are compared on an annual basis.",
    ],
    [
      /^Настройки источника · (.+)$/,
      "Manba sozlamalari · $1",
      "Source settings · $1",
    ],
    [/^Множитель: (.+)$/, "Koeffitsiyent: $1", "Multiplier: $1"],
    [/^(\d+) \/ 20 файлов$/, "$1 / 20 fayl", "$1 / 20 files"],
    [/^Осмотр № (.+) · (.+)$/, "Ko‘rik № $1 · $2", "Inspection № $1 · $2"],
    [/^№ (.+) · версия (\d+)$/, "№ $1 · versiya $2", "№ $1 · version $2"],
    [
      /^Акт № (.+) · (.+) · Подлежит подтверждению андеррайтером · Не является кредитным скорингом$/,
      "Dalolatnoma № $1 · $2 · Anderrayter tasdig‘i talab qilinadi · Kredit skoringi emas",
      "Report № $1 · $2 · Subject to underwriter confirmation · Not a credit score",
    ],
    [
      /^Строк: (\d+) · Добавить: (\d+) · Изменить: (\d+) · Ошибок: (\d+)$/,
      "Satrlar: $1 · Qo‘shish: $2 · O‘zgartirish: $3 · Xatolar: $4",
      "Rows: $1 · Add: $2 · Update: $3 · Errors: $4",
    ],
    [
      /^Последний запуск фоновых задач: (.+)$/,
      "Fon vazifalarining oxirgi ishga tushishi: $1",
      "Last background worker run: $1",
    ],
    [
      /^Режим: (.+) · ИИ отключён$/,
      "Rejim: $1 · SI o‘chirilgan",
      "Mode: $1 · AI disabled",
    ],
    [
      /^Калибровка утверждена. Поправка: (.+)%$/,
      "Kalibrlash tasdiqlandi. Tuzatish: $1%",
      "Calibration approved. Adjustment: $1%",
    ],
  ];
  function text(source) {
    if (language === "ru") return source;
    const key = normalize(source);
    const translated = catalog[key]?.[language];
    if (translated) return source.replace(source.trim(), translated);
    for (const [pattern, uz, en] of patterns) {
      if (pattern.test(key))
        return key.replace(pattern, language === "uz" ? uz : en);
    }
    return source;
  }
  function translateNode(node) {
    if (
      !node.parentElement ||
      node.parentElement.closest(
        "script,style,textarea,pre,[data-no-translate]",
      )
    )
      return;
    const old = records.get(node);
    const original =
      old && node.nodeValue === old.rendered ? old.original : node.nodeValue;
    const rendered = text(original);
    records.set(node, { original, rendered });
    if (node.nodeValue !== rendered) node.nodeValue = rendered;
  }
  function apply(root = document.body) {
    const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
    while (walker.nextNode()) translateNode(walker.currentNode);
    root.querySelectorAll?.("[placeholder],[aria-label]").forEach((el) => {
      for (const attr of ["placeholder", "aria-label"]) {
        if (!el.hasAttribute(attr)) continue;
        const key = `i18n${attr.replaceAll("-", "")}`;
        if (!el.dataset[key]) el.dataset[key] = el.getAttribute(attr);
        el.setAttribute(attr, text(el.dataset[key]));
      }
    });
    document.documentElement.lang = language;
  }
  let queued = false;
  const observer = new MutationObserver(() => {
    if (queued) return;
    queued = true;
    queueMicrotask(() => {
      queued = false;
      observer.disconnect();
      apply();
      observe();
    });
  });
  function observe() {
    observer.observe(document.body, {
      childList: true,
      characterData: true,
      subtree: true,
    });
  }
  const ready = fetch("/static/locales.json")
    .then((r) => r.json())
    .then((data) => {
      catalog = data;
      apply();
      observe();
    });
  function setLocale(locale) {
    language = ["ru", "uz", "en"].includes(locale) ? locale : "ru";
    localStorage.setItem("surveyor-language", language);
    apply();
  }
  return { ready, text, setLocale };
})();
