"use strict";

window.SurveyorFactorPricing = {
  catalogue: null,
  async load() {
    this.catalogue ||= await api("/factor-catalogue");
    return this.catalogue;
  },
  entries(cls) {
    return (this.catalogue?.entries || []).filter(
      (r) => !r.classes.length || r.classes.includes(Number(cls)),
    );
  },
  renderAnswers(container, template, answers = {}) {
    const policy = template?.factor_policy;
    container.innerHTML = "";
    if (!policy) return;
    container.innerHTML = `<h3>Факторы тарифа</h3><p class="notice">${template.approved_by && !template.factor_calibration_stale ? "Коэффициенты утверждены актуарием" : "Коэффициенты не применяются до актуального утверждения актуария"}</p><p class="form-hint">Выберите состояние каждого фактора и укажите основание. Незаполненные факторы не меняют ставку и попадут в «Уточнить». Для остальных подгрупп выберите «Не применимо». Старые множители риска повторно не применяются.</p>${this.entries(
      policy.insurance_class,
    )
      .map((r) => {
        const a = answers[r.id] || {};
        const c = policy.coefficients[r.id] || {};
        return `<details class="factor-answer" data-factor="${r.id}" ${a.choice ? "open" : ""}><summary data-no-translate>${esc(r.label)} · ${r.page}</summary><p class="small" data-no-translate>+ ${esc(r.raises)}<br>− ${esc(r.lowers)}</p>${select(`factor_choice_${r.id}`, "Состояние фактора", [["", "Не заполнено"], ...(r.raises !== "—" ? [["raises", `Повышает · ${c.raises ?? "?"}`]] : []), ...(r.lowers !== "—" ? [["lowers", `Понижает · ${c.lowers ?? "?"}`]] : []), ["neutral", "Нейтрально · 1"], ["not_applicable", "Не применимо · 1"]], a.choice || "")}<label>Основание / источник<textarea data-factor-evidence maxlength="1000">${esc(a.evidence || "")}</textarea></label></details>`;
      })
      .join("")}`;
    for (const row of $$(".factor-answer", container)) {
      const choice = $("select", row),
        evidence = $("textarea", row);
      const sync = () => {
        evidence.required = !!choice.value;
        evidence.minLength = choice.value ? 3 : 0;
      };
      choice.onchange = sync;
      sync();
    }
  },
  readAnswers() {
    return Object.fromEntries(
      $$(".factor-answer")
        .filter((r) => $("select", r).value)
        .map((r) => [
          r.dataset.factor,
          { choice: $("select", r).value, evidence: $("textarea", r).value },
        ]),
    );
  },
  async edit(template) {
    await this.load();
    const old = template.factor_policy || {};
    modal(
      `<h2>Факторы тарифа: новая версия</h2><p class="notice">Числовых коэффициентов в PDF нет. Пустое поле означает «не задано». Любое изменение требует нового утверждения актуарием.</p><form id="factor-policy-form">${select(
        "insurance_class",
        "Класс страхования",
        Array.from({ length: 18 }, (_, i) => [String(i + 1), String(i + 1)]),
        String(
          old.insurance_class ||
            { vehicle: 3, fire: 8, property: 9 }[template.class_code] ||
            Number(template.class_code) ||
            3,
        ),
      )}<label>Обоснование коэффициентов и применимости<textarea name="rationale" required minlength="10" maxlength="3000">${esc(old.rationale || "")}</textarea></label><div id="factor-coefficients"></div><button class="primary" type="submit">Сохранить факторную версию</button></form>`,
    );
    const render = () => {
      $("#factor-coefficients").innerHTML = this.entries(
        $("[name=insurance_class]").value,
      )
        .map((r) => {
          const c = old.coefficients?.[r.id] || {};
          return `<details data-coefficient="${r.id}"><summary data-no-translate>${esc(r.label)} · ${r.id} · ${r.page}</summary><p class="small" data-no-translate>+ ${esc(r.raises)}<br>− ${esc(r.lowers)}</p><div class="form-grid">${r.raises !== "—" ? field(`raises_${r.id}`, "Повышающий коэффициент (>1)", c.raises || "", "number", 'min="1.00000001" max="10" step="0.00000001"') : ""}${r.lowers !== "—" ? field(`lowers_${r.id}`, "Понижающий коэффициент (<1)", c.lowers || "", "number", 'min="0.1" max="0.99999999" step="0.00000001"') : ""}</div></details>`;
        })
        .join("");
    };
    render();
    $("[name=insurance_class]").onchange = render;
    bindForm("#factor-policy-form", async (values) => {
      const coefficients = {};
      for (const row of $$("[data-coefficient]")) {
        const pair = {};
        for (const side of ["raises", "lowers"]) {
          const input = $(`[name=${side}_${row.dataset.coefficient}]`, row);
          if (input?.value) pair[side] = input.value;
        }
        if (Object.keys(pair).length)
          coefficients[row.dataset.coefficient] = pair;
      }
      await post(`/admin/templates/${template.id}/factors`, {
        policy: {
          insurance_class: Number(values.insurance_class),
          coefficients,
          rationale: values.rationale,
        },
      });
      $("#modal").close();
      state.templates = await api("/templates");
      await adminTemplates();
    });
  },
  async experience(template) {
    await this.load();
    const current = await api(
      `/admin/templates/${template.id}/factor-experience`,
    );
    modal(
      `<h2>Статистика факторов</h2><p>Загрузите агрегированные данные без персональных сведений: factor_id, choice (raises / lowers / neutral), year, exposure (страховые годы), claims, payments (UZS). Каждый сегмент должен включать одинаковые последние 3–5 полных лет. Суммы выплат должны относиться к тем же экспозициям и сопоставимому покрытию.</p><p class="notice">Новая загрузка целиком заменяет текущий набор для класса и отменяет применение прежней статистической калибровки. История и старые акты сохраняются.</p><details><summary>Формат CSV и коды факторов</summary><pre data-no-translate>factor_id,choice,year,exposure,claims,payments</pre>${this.entries(
        template.factor_policy.insurance_class,
      )
        .map((r) => `<p data-no-translate>${r.id} — ${esc(r.label)}</p>`)
        .join(
          "",
        )}</details><form id="factor-experience-form"><input type="file" name="file" accept=".csv,.xlsx" required><button class="secondary" type="submit">Предпросмотр статистики</button></form><div id="factor-experience-preview"></div><p>${current.batch ? `SHA256: ${esc(current.batch.sha256)} · ${current.batch.rows.length}` : "Статистика не загружена"}</p>${current.batch ? jsonDetails(current.batch.rows) : ""}${state.user.role === "actuary" && current.batch ? `<h3>Предложить калибровку</h3><p>Метод: выплаты / страховые годы сегмента, делённые на значение нейтрального сегмента. Отношение ограничивается выбранным отклонением от 1. Это однофакторная оценка; корреляция, достаточность данных и развитие убытков требуют проверки актуарием.</p><form id="factor-calibration-form"><div class="form-grid">${field("minimum_exposure", "Минимум страховых лет на сегмент", "", "number", 'required min="0.0001" max="1000000000000" step="any"')}${field("max_change", "Максимальное отклонение от 1 (0.2 = 20%)", "", "number", 'required min="0.00000001" max="0.9" step="any"')}</div><label>Обоснование метода и ограничений<textarea name="rationale" required minlength="10" maxlength="3000"></textarea></label><label class="check"><input name="method_confirmed" type="checkbox" required>Метод и сопоставимость сегментов проверены актуарием</label><button class="primary" type="submit">Рассчитать новую версию для утверждения</button></form>` : ""}`,
    );
    bindForm("#factor-experience-form", async (_, form) => {
      const preview = await api(
        `/admin/templates/${template.id}/factor-experience/preview`,
        { method: "POST", body: new FormData(form) },
      );
      $("#factor-experience-preview").innerHTML =
        `<p>${preview.rows.length}</p>${preview.rows
          .filter((r) => r.error)
          .map((r) => `<p class="form-error">${r.row}: ${esc(r.error)}</p>`)
          .join(
            "",
          )}${jsonDetails(preview.rows)}${preview.can_confirm ? '<button type="button" class="primary" id="confirm-factor-experience">Подтвердить замену статистики</button>' : ""}`;
      if (preview.can_confirm)
        $("#confirm-factor-experience").onclick = async () => {
          try {
            await post(`/admin/factor-experience/${preview.id}/confirm`);
            await this.experience(template);
          } catch (e) {
            toast(e.message, true);
          }
        };
    });
    if ($("#factor-calibration-form"))
      bindForm("#factor-calibration-form", async (d) => {
        await post(`/admin/templates/${template.id}/factor-calibration`, {
          batch_id: current.batch.id,
          minimum_exposure: d.minimum_exposure,
          max_change: d.max_change,
          rationale: d.rationale,
          method_confirmed: true,
        });
        $("#modal").close();
        state.templates = await api("/templates");
        await adminTemplates();
      });
  },
};
