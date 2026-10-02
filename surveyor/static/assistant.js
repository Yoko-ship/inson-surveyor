"use strict";

window.SurveyorAssistant = (() => {
  const watches = new WeakMap();
  function jobStatus(job) {
    const labels = {
      queued: "В очереди",
      running: "ИИ анализирует материалы…",
      completed: "Готово к проверке",
      reviewed: "Проверено",
      failed: "Ошибка обработки",
      stale: "Исходные данные изменились",
      cancelled: "Отменено",
    };
    return `${window.SurveyorI18n.text(labels[job.status] || job.status)} · ${job.attempts}/3`;
  }
  function watch(job, target, complete) {
    const token = {};
    watches.set(target, token);
    const poll = async () => {
      if (!target.isConnected || watches.get(target) !== token) return;
      target.replaceChildren();
      const status = document.createElement("p");
      status.setAttribute("role", "status");
      status.textContent = jobStatus(job);
      target.append(status);
      if (job.error) {
        const error = document.createElement("p");
        error.textContent = job.error;
        target.append(error);
      }
      if (job.status === "completed") return complete(job);
      if (!["queued", "running"].includes(job.status)) return;
      const note = document.createElement("p");
      note.textContent =
        "Можно закрыть Mini App. Задание продолжится на сервере; результат сохранится здесь.";
      target.append(note);
      const cancel = document.createElement("button");
      cancel.type = "button";
      cancel.className = "secondary";
      cancel.textContent = "Отменить задание";
      cancel.onclick = async () => {
        cancel.disabled = true;
        try {
          await post(`/ai-pilot/jobs/${job.id}/cancel`);
        } catch (error) {
          toast(error.message, true);
        }
      };
      target.append(cancel);
      setTimeout(async () => {
        if (!target.isConnected || watches.get(target) !== token) return;
        try {
          job = await api(`/ai-pilot/jobs/${job.id}`);
          await poll();
        } catch (error) {
          status.textContent = error.message;
        }
      }, 2000);
    };
    poll();
  }
  async function page() {
    const survey = state.survey;
    const target = $("#survey-body");
    const guide = await api(`/surveys/${survey.id}/guidance`);
    if (!target.isConnected) return;
    const info =
      state.codexDocuments && survey.owner_id === state.user.id
        ? await api("/ai-pilot")
        : null;
    const jobs = info ? await api(`/ai-pilot/surveys/${survey.id}/jobs`) : [];
    const aiQuestions = jobs
      .filter((j) => ["completed", "reviewed"].includes(j.status))
      .filter(
        (j, i, all) => all.findIndex((item) => item.kind === j.kind) === i,
      )
      .flatMap((j) =>
        (j.result.questions || []).map((text, i) => ({
          id: `ai_${j.id}_${i}`,
          text,
          kind: "AI",
        })),
      );
    const questions = [...guide.questions, ...aiQuestions];
    target.innerHTML = `<section class="panel"><h3>Вопросы по осмотру</h3><p>Ответьте по материалам осмотра. Ответы сохраняются отдельно от расчётных значений.</p><form id="guidance-form">${questions.map((q, i) => `<label>${esc(q.kind === "risk" ? named(q.text) : q.text)}<textarea name="answer_${i}" maxlength="2000" data-no-translate>${esc(guide.answers[q.id] || "")}</textarea></label>`).join("")}<button type="submit" class="primary">Сохранить ответы</button><p class="form-error"></p></form></section><section class="panel"><h3>Расхождения документов</h3>${guide.conflicts.map((c) => `<p><strong>${esc(named(c.field))}</strong>: ${c.values.map((v) => `<span data-no-translate>${esc(v.filename)} = ${esc(v.value)}</span>`).join(" / ")} · ${esc(c.entered ?? "—")}</p>`).join("") || `<p>Расхождения в извлечённых значениях не обнаружены.</p>`}</section><section class="panel"><h3>Обоснование расчёта</h3><p>Значения рассчитаны кодом по выбранной версии тарифа. ИИ не назначает цены и не утверждает условия.</p>${guide.explanation.map((row) => `<p>${esc(named(row.field))}: <span data-no-translate>${esc(Array.isArray(row.value) ? row.value.map(named).join(" · ") : row.field === "risk_level" ? named(row.value) : row.value)}</span></p>`).join("") || `<p>Сохраните исходные данные осмотра для расчёта.</p>`}${guide.context.product ? `<p>Версия тарифа: <span data-no-translate>${esc(guide.context.product.version_id)}</span></p>` : ""}</section>${info ? analysisForm(survey, info) : ""}<section class="panel" id="analysis-jobs"><h3>Задания ИИ</h3>${jobs.map((j) => `<div class="file-card"><p>${esc(jobStatus(j))}</p>${j.error ? `<p>${esc(j.error)}</p>` : ""}${j.kind === "document" ? "" : `<button type="button" class="secondary" data-job="${j.id}">Открыть результат</button>`}</div>`).join("") || `<p>Заданий пока нет.</p>`}</section><div id="assistant-result" class="panel" hidden></div><section class="panel"><h3>Проверенные наблюдения</h3>${guide.reviews
      .map(
        (r) =>
          `<div class="file-card"><p>${esc(r.reviewer_name)} · ${esc(r.reviewed_at)}</p>${r.stale ? `<p class="notice">Проверка устарела: исходные данные изменились.</p>` : ""}${r.fields
            .filter((f) => f.decision !== "rejected")
            .map((f) => `<p data-no-translate>${esc(f.reviewed_text)}</p>`)
            .join("")}</div>`,
      )
      .join("")}</section>`;
    if (survey.owner_id !== state.user.id)
      $$("textarea,button", $("#guidance-form")).forEach((el) => {
        el.disabled = true;
      });
    bindForm("#guidance-form", async (_, form) => {
      const answers = Object.fromEntries(
        questions.map((q, i) => [q.id, form.elements[`answer_${i}`].value]),
      );
      await api(`/surveys/${survey.id}/guidance`, {
        method: "PUT",
        body: JSON.stringify({ revision: survey.revision, answers }),
      });
      await openSurvey(survey.id, "assistant");
    });
    if (info) bindAnalysis(survey, info);
    action("[data-job]", (button) =>
      openJob(
        jobs.find((j) => j.id === button.dataset.job),
        survey,
      ),
    );
    const active = jobs.find(
      (j) => ["queued", "running"].includes(j.status) && j.kind !== "document",
    );
    if (active) openJob(active, survey);
  }
  function analysisForm(survey, info) {
    return `<section class="panel"><h3>Анализ материалов</h3>${info.jobs_ready === false ? `<p class="notice">Фоновый обработчик недоступен. Задание начнётся после его запуска.</p>` : ""}<form id="assistant-analyze">${select(
      "kind",
      "Задача",
      [
        ["inspection", "Сравнение документов и пояснения"],
        ["photo", "Видимые условия на фотографиях"],
      ],
      "inspection",
    )}<p>Выберите материалы. Общий лимит: 10 страниц или фото и 60 000 символов.</p>${survey.documents.map((d) => `<label class="check"><input type="checkbox" name="document" value="${d.id}"><span data-no-translate>${esc(d.filename)}</span></label>`).join("")}<label class="check"><input type="checkbox" name="consent" required>${info.provider === "ollama" ? "Обработать выбранные материалы локальной моделью." : "Отправить выбранные материалы и контекст осмотра в OpenAI через подключение Codex приложения. Используется общий лимит подписки."}</label><button type="submit" class="primary" ${info.ready ? "" : "disabled"}>Начать анализ</button><p class="form-error"></p></form></section>`;
  }
  function bindAnalysis(survey, info) {
    bindForm("#assistant-analyze", async (_, form) => {
      const documentIds = $$("[name=document]:checked", form).map(
        (el) => el.value,
      );
      if (!documentIds.length)
        throw new Error("Выберите хотя бы один документ.");
      const job = await post(`/ai-pilot/surveys/${survey.id}/jobs`, {
        revision: survey.revision,
        kind: form.elements.kind.value,
        document_ids: documentIds,
        cloud_consent: true,
        config_revision: info.config_revision,
        locale: state.locale,
      });
      openJob(job, survey);
    });
  }
  function openJob(job, survey) {
    const target = $("#assistant-result");
    target.hidden = false;
    watches.delete(target);
    if (job.status === "reviewed") {
      target.textContent =
        "Результат уже проверен. Решения сохранены в осмотре.";
      return;
    }
    watch(job, target, (done) => showResult(done, survey, target));
  }
  function showResult(job, survey, target) {
    const rows = [...job.result.findings, ...job.result.explanation];
    target.innerHTML = `<h3>Проверка предложений ИИ</h3><p>Отметьте подтверждённые наблюдения. Неотмеченные предложения будут отклонены. Фотографии не подтверждают скрытые дефекты или безопасность объекта.</p><form id="assistant-review">${rows.map((row, i) => `<section class="file-card"><label class="check"><input type="checkbox" name="use_${i}">${esc(named(row.category))}</label><div data-ai-text="${i}"></div><label>Проверенное наблюдение<textarea name="text_${i}" maxlength="1500" data-no-translate>${esc(row.text)}</textarea></label>${row.citations.map((cite) => `<blockquote data-no-translate>${esc(cite.filename || cite.source_id)}: ${esc(cite.quote || "Фото: требуется визуальная проверка")}</blockquote>${cite.quote_found_in_text ? "" : `<p class="notice">Сверьте наблюдение с оригиналом.</p>`}`).join("")}</section>`).join("")}<label>Причина / результат проверки<textarea name="reason" required minlength="5" maxlength="1000"></textarea></label><label class="check"><input type="checkbox" name="confirmed" required>Я сверил(а) наблюдения и источники.</label><button type="submit" class="primary">Сохранить проверку</button><p class="form-error"></p></form>${job.result.questions.length ? `<h3>Дополнительные вопросы</h3>${job.result.questions.map((q) => `<p data-no-translate>${esc(q)}</p>`).join("")}<button type="button" class="secondary" id="refresh-guidance">Перейти к ответам</button>` : ""}`;
    rows.forEach((row, i) =>
      window.SurveyorAIText.render(
        $(`[data-ai-text="${i}"]`, target),
        row.text,
        job.result.display_mode,
      ),
    );
    if ($("#refresh-guidance"))
      $("#refresh-guidance").onclick = () => openSurvey(survey.id, "assistant");
    bindForm("#assistant-review", async (_, form) => {
      const accepted = Object.fromEntries(
        rows
          .filter((row, i) => form.elements[`use_${i}`].checked)
          .map((row) => [
            row.id,
            form.elements[`text_${rows.indexOf(row)}`].value,
          ]),
      );
      await post(`/ai-pilot/jobs/${job.id}/review`, {
        revision: survey.revision,
        accepted,
        reason: form.elements.reason.value,
        review_confirmed: true,
      });
      await openSurvey(survey.id, "assistant");
    });
  }
  return { page, watch };
})();
