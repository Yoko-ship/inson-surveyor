"use strict";

window.SurveyorCodexPilot = (() => {
  async function page() {
    const info = await api("/ai-pilot");
    $("#content").innerHTML =
      heading(
        info.documents_enabled
          ? "Codex · мои документы"
          : "Codex · учебный пилот",
        "Распознавание через ваш вход в Codex. Все значения требуют проверки.",
      ) +
      (info.documents_enabled ? documentForm(info.ready) : "") +
      `<section class="panel"><h2>Учебные примеры</h2><p class="notice">Выбранный учебный пример отправляется в облако OpenAI и расходует лимит Codex.</p><p>${esc(info.message)}</p><form id="codex-pilot-form">${select(
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
          ? `<img class="pilot-scan" src="${esc(info.sample_image || "/api/ai-pilot/sample.png")}" alt="Учебный документ" />`
          : `<pre class="reference-text" data-no-translate>${esc(sample.text)}</pre>`;
      $("#codex-result").hidden = true;
    };
    form.elements.sample_id.onchange = preview;
    preview();
    if (info.documents_enabled) bindDocumentForm(info.ready);
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
  function documentForm(ready) {
    return `<section class="panel"><h2>Загрузить документ</h2><p>PDF до 10 страниц, фото, DOCX, XLSX, TXT или CSV. До 15 МБ и 60 000 символов. Результат появится здесь для проверки; значения не переносятся в осмотр автоматически.</p><form id="codex-document-form"><input type="file" name="file" required accept=".pdf,.jpg,.jpeg,.png,.webp,.docx,.xlsx,.txt,.csv"><label class="check"><input type="checkbox" name="cloud_consent" required>Отправить выбранный документ в OpenAI для анализа через мою подписку Codex.</label><button type="submit" class="primary" ${ready ? "" : "disabled"}>Анализировать документ</button><p class="form-hint">Mac и подключение к интернету должны оставаться включёнными. Если авторизация устарела, откройте Mini App заново.</p><p role="status" id="document-progress"></p><p class="form-error"></p></form><div id="document-result" hidden></div></section>`;
  }
  function bindDocumentForm(ready) {
    const form = $("#codex-document-form");
    form.onsubmit = async (event) => {
      event.preventDefault();
      const button = form.querySelector("button");
      const progress = $("#document-progress");
      const output = $("#document-result");
      const error = form.querySelector(".form-error");
      const data = new FormData(form);
      data.set("cloud_consent", "true");
      button.disabled = true;
      output.hidden = true;
      error.textContent = "";
      progress.textContent =
        "Codex читает документ. Это может занять до полутора минут…";
      try {
        const result = await api("/ai-pilot/analyze", {
          method: "POST",
          body: data,
        });
        if (!form.isConnected) return;
        output.innerHTML = `<h3>Предложения для проверки</h3><p>Сверьте значения и цитаты с оригиналом. Для сканов цитаты не проверены автоматически. Результат не сохранён в осмотр.</p><div class="table-wrap"><table><thead><tr><th>Поле</th><th>Предложение Codex</th><th>Цитата</th></tr></thead><tbody>${result.fields.map((row) => `<tr><td>${esc(named(row.field))}</td><td data-no-translate>${esc(row.value ?? "—")}</td><td data-no-translate>${esc(row.quote)}</td></tr>`).join("")}</tbody></table></div>`;
        output.hidden = false;
      } catch (err) {
        error.textContent = err.message;
      } finally {
        progress.textContent = "";
        button.disabled = !ready;
      }
    };
  }
  return { page };
})();
