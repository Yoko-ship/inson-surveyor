"use strict";

window.SurveyorInspectionAI = (() => {
  const kinds = [
    ["photo", "Фото объекта"],
    ["contract", "Договор"],
    ["branch_request", "Запрос филиала"],
    ["report", "Отчёт"],
    ["document", "Документ"],
  ];
  async function open(doc) {
    const survey = state.survey;
    const path = `/ai-pilot/documents/${doc.id}`;
    const [info, pending] = await Promise.all([
      api("/ai-pilot"),
      api(`${path}/proposal`),
    ]);
    modal(
      `<h2>ИИ · проверка документа</h2><p><a href="/api/documents/${doc.id}/download" target="_blank" rel="noopener" data-no-translate>${esc(doc.filename)} ↗</a></p><form id="inspection-ai-analyze"><label class="check"><input type="checkbox" name="consent" required>${info.provider === "ollama" ? "Обработать выбранный документ локальной моделью Ollama." : "Отправить выбранный документ в OpenAI для анализа через мою подписку Codex."}</label><button class="secondary" type="submit" ${info.ready ? "" : "disabled"}>Анализировать документ</button><p role="status"></p><p class="form-error"></p></form><div id="inspection-ai-result"></div>`,
    );
    const form = $("#inspection-ai-analyze");
    const output = $("#inspection-ai-result");
    if (pending) show(pending, doc, survey, output);
    bindForm("#inspection-ai-analyze", async () => {
      $("[role=status]", form).textContent =
        "ИИ читает документ. Это может занять до полутора минут…";
      try {
        const proposal = await post(`${path}/analyze`, {
          revision: survey.revision,
          config_revision: info.config_revision,
          cloud_consent: true,
          locale: state.locale,
        });
        if (output.isConnected) show(proposal, doc, survey, output);
      } finally {
        $("[role=status]", form).textContent = "";
      }
    });
  }
  function show(proposal, doc, survey, output) {
    if (proposal.stale) {
      output.innerHTML = `<p class="notice">Осмотр изменился. Повторите анализ для проверки предложений.</p>`;
      return;
    }
    output.innerHTML = `<h3>Предложения для проверки</h3><div class="ai-summary"></div><p>Выберите поля для сохранения и исправьте значения при необходимости. Остальные предложения будут отклонены.</p><form id="inspection-ai-review">${select("kind", "Вид документа", kinds, doc.extracted.kind)}${proposal.fields.map((row, i) => `<section class="file-card"><label class="check"><input type="checkbox" name="use_${i}">${esc(named(row.field))}</label><p class="small"><span>Текущее значение</span>: <span data-no-translate>${esc(doc.extracted.fields[row.field]?.value ?? "—")}</span></p><p class="small"><span>Предложение ИИ</span>: <span data-no-translate>${esc(row.value ?? "—")}</span></p><blockquote data-no-translate>${esc(row.quote)}</blockquote><p class="form-hint">${row.quote_found_in_text ? "Цитата найдена в тексте. Проверьте контекст." : "Цитата не проверена автоматически. Сверьте с оригиналом."}</p>${field(`value_${i}`, "Проверенное значение", row.value ?? "", row.field.startsWith("contract_") ? "date" : "text")}</section>`).join("")}<label>Причина / результат проверки<textarea name="reason" required minlength="5" maxlength="1000"></textarea></label><label class="check"><input type="checkbox" name="review_confirmed" required>Я сверил(а) выбранные значения и цитаты с оригиналом.</label><button class="primary" type="submit">Сохранить проверку</button><p class="form-error"></p></form>`;
    window.SurveyorAIText.render(
      $(".ai-summary", output),
      proposal.summary,
      proposal.display_mode,
    );
    bindForm("#inspection-ai-review", async (_, form) => {
      const fields = {};
      proposal.fields.forEach((row, i) => {
        if (form.elements[`use_${i}`].checked)
          fields[row.field] = form.elements[`value_${i}`].value || null;
      });
      await post(
        `/ai-pilot/documents/${doc.id}/proposals/${proposal.id}/review`,
        {
          revision: proposal.revision,
          kind: form.elements.kind.value,
          fields,
          reason: form.elements.reason.value,
          review_confirmed: true,
        },
      );
      $("#modal").close();
      await openSurvey(survey.id, "review");
    });
  }
  // Explicitly copy reviewed document values into the form, including on reopened inspections.
  function bindTransfer() {
    const form = $("#review-form");
    const docs = state.survey.documents.filter(
      (d) => d.extracted.ai_reviews?.length,
    );
    if (!docs.length) return;
    const panel = document.createElement("section");
    panel.className = "panel";
    panel.innerHTML = `<h3>Проверенные поля документов</h3><p>Перенесите значения выбранного документа в форму, затем проверьте и сохраните осмотр.</p>${docs.map((doc) => `<button type="button" class="secondary" data-transfer-document="${doc.id}" data-no-translate>${esc(doc.filename)}</button>`).join(" ")}<p role="status"></p>`;
    $(".two-col > div", form).prepend(panel);
    panel.querySelectorAll("[data-transfer-document]").forEach((button) => {
      button.onclick = () => {
        const doc = docs.find((d) => d.id === button.dataset.transferDocument);
        const transferred = [];
        const reviewedKeys = new Set(
          doc.extracted.ai_reviews.flatMap((review) =>
            review.fields
              .filter((row) => row.decision !== "rejected")
              .map((row) => row.field),
          ),
        );
        if (
          doc.extracted.fields.term_days?.derived_from === "contract_dates" &&
          reviewedKeys.has("contract_start") &&
          reviewedKeys.has("contract_end")
        )
          reviewedKeys.add("term_days");
        for (const [key, item] of Object.entries(doc.extracted.fields)) {
          if (reviewedKeys.has(key) && form.elements[key]) {
            form.elements[key].value = item.value ?? "";
            transferred.push(`${named(key)} = ${item.value}`);
          }
        }
        form.elements.manual_review_confirmed.checked = false;
        const status = $("[role=status]", panel);
        status.setAttribute("data-no-translate", "");
        status.textContent = transferred.join(" · ");
      };
    });
  }
  return { open, bindTransfer };
})();
