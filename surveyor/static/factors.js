"use strict";

window.SurveyorFactors = {
  async mount(container) {
    const data = await api("/policy/factors");
    container.insertAdjacentHTML(
      "beforeend",
      `<section class="panel" id="factor-guide"><h3>Факторы тарифа по классам</h3><p class="notice">Не калибровано. Документ задаёт направление влияния, но не числовые коэффициенты. Этот справочник сохраняет исходный документ. Факторный расчёт настраивается в шаблонах классов и требует утверждения актуарием.</p><p class="form-hint">Для обязательного страхования применяется нормативный тариф. Размеры поправок и метод калибровки утверждает актуарий.</p><div class="form-grid">${select("factor_class", "Класс страхования", [["", "Все"], ...Array.from({ length: 18 }, (_, i) => [String(i + 1), String(i + 1)])])}${field("factor_search", "Поиск фактора")}</div><p id="factor-count" aria-live="polite"></p><div class="table-wrap"><table><thead><tr><th>Фактор / подгруппа</th><th>Повышает</th><th>Понижает</th><th>Страница</th></tr></thead><tbody id="factor-rows" data-no-translate></tbody></table></div><details><summary>Полный текст предоставленного документа</summary><p class="form-hint">Текст источника сохранён дословно; раздел о состоянии системы отражает мнение автора документа.</p><div data-no-translate>${data.pages.map((p) => `<details><summary>${p.page}</summary><p class="reference-text">${esc(p.text)}</p></details>`).join("")}</div></details><p class="small muted" data-no-translate>${esc(data.date)} · SHA256 ${esc(data.sha256)}</p></section>`,
    );
    const render = () => {
      const cls = Number($("[name=factor_class]").value);
      const query = $("[name=factor_search]").value.trim().toLocaleLowerCase();
      const rows = data.entries.filter(
        (r) =>
          (!cls || !r.classes.length || r.classes.includes(cls)) &&
          `${r.label} ${r.raises} ${r.lowers} ${r.section}`
            .toLocaleLowerCase()
            .includes(query),
      );
      $("#factor-count").textContent =
        `${rows.length} / ${data.entries.length}`;
      $("#factor-rows").innerHTML = rows
        .map(
          (r) =>
            `<tr><td><strong>${esc(r.label)}</strong><p class="small muted">${esc(r.section)}</p></td><td>${esc(r.raises)}</td><td>${esc(r.lowers)}</td><td>${r.page}</td></tr>`,
        )
        .join("");
    };
    $("[name=factor_class]").onchange = render;
    $("[name=factor_search]").oninput = render;
    render();
  },
};
