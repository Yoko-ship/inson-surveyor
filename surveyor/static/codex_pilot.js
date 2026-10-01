"use strict";

window.SurveyorCodexPilot = (() => {
  async function page() {
    const info = await api("/ai-pilot");
    $("#content").innerHTML =
      heading(
        "Codex · учебный пилот",
        "Распознавание вымышленных документов через ваш вход в Codex.",
      ) +
      `<section class="panel"><p class="notice">Выбранный учебный пример отправляется в облако OpenAI и расходует лимит Codex. Доступны только встроенные вымышленные документы.</p><p>${esc(info.message)}</p><form id="codex-pilot-form">${select(
        "sample_id",
        "Учебный пример",
        info.samples.map((s) => [s.id, s.title]),
        "text",
      )}<div id="codex-sample"></div><button type="submit" class="primary" ${info.ready ? "" : "disabled"}>Прочитать через Codex</button><p id="codex-progress" role="status"></p><p class="form-error"></p></form></section><section class="panel" id="codex-result" hidden></section>`;
    const form = $("#codex-pilot-form");
    const preview = () => {
      const sample = info.samples.find(
        (s) => s.id === form.elements.sample_id.value,
      );
      $("#codex-sample").innerHTML =
        sample.id === "scan"
          ? '<img class="pilot-scan" src="/api/ai-pilot/sample.png" alt="Учебный документ" />'
          : `<pre class="reference-text" data-no-translate>${esc(sample.text)}</pre>`;
      $("#codex-result").hidden = true;
    };
    form.elements.sample_id.onchange = preview;
    preview();
    form.onsubmit = async (event) => {
      event.preventDefault();
      const sampleId = form.elements.sample_id.value;
      const button = form.querySelector("button[type=submit]");
      button.disabled = true;
      form.elements.sample_id.disabled = true;
      const progress = form.querySelector("#codex-progress");
      const output = $("#codex-result");
      const error = form.querySelector(".form-error");
      error.textContent = "";
      output.hidden = true;
      progress.textContent =
        "Codex читает пример. Это может занять до двух минут…";
      try {
        const result = await post("/ai-pilot/run", { sample_id: sampleId });
        if (!form.isConnected) return;
        output.innerHTML = `<h2>Предложения для проверки</h2><p>Сравнение с известными значениями учебного примера. Результат не сохранён в осмотр.</p><div class="table-wrap"><table><thead><tr><th>Поле</th><th>Ответ Codex</th><th>Ожидаемое значение</th><th>Проверка</th></tr></thead><tbody>${result.fields.map((row) => `<tr><td>${esc(named(row.field))}</td><td data-no-translate>${esc(row.value ?? "—")}</td><td data-no-translate>${esc(row.expected ?? "—")}</td><td>${row.matches ? "✓" : "✕"}</td></tr>`).join("")}</tbody></table></div><h3>Цитаты из документа</h3>${result.fields
          .filter((row) => row.value !== null)
          .map(
            (row) =>
              `<p><strong>${esc(named(row.field))}:</strong> <span data-no-translate>${esc(row.quote)}</span></p>`,
          )
          .join(
            "",
          )}<p class="notice">Все предложения требуют проверки сотрудником. Этот тест не подтверждает качество распознавания реальных документов.</p>`;
        output.hidden = false;
      } catch (err) {
        error.textContent = err.message;
      } finally {
        progress.textContent = "";
        button.disabled = !info.ready;
        form.elements.sample_id.disabled = false;
      }
    };
  }
  return { page };
})();
