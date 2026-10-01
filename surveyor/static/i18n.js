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
  function text(source) {
    if (language === "ru") return source;
    const key = normalize(source);
    const translated = catalog[key]?.[language];
    return translated ? source.replace(source.trim(), translated) : source;
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
