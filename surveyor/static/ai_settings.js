"use strict";

window.SurveyorAISettings = (() => {
  async function open() {
    const info = await api("/ai-pilot/settings");
    let revision = info.revision;
    function render(config, notice = "") {
      modal(
        `<h2>Настройки ИИ</h2><p>Промпты и правила сохраняются при смене модели. Изменения действуют со следующего запроса.</p><p role="status" id="ai-settings-notice">${esc(notice)}</p><form id="ai-settings-form"><label class="check"><input name="enabled" type="checkbox" ${config.enabled ? "checked" : ""}>Включить ИИ</label><div class="form-grid">${select(
          "provider",
          "Провайдер",
          info.providers.map((p) => [p.id, p.label]),
          config.provider,
        )}${select(
          "display_mode",
          "Оформление ответа",
          [
            ["formatted", "Форматированный текст"],
            ["plain", "Обычный текст"],
          ],
          config.display_mode,
        )}${field("codex_model", "Модель Codex (пусто — по умолчанию)", config.codex.model)}${select(
          "reasoning_effort",
          "Глубина анализа Codex",
          [
            ["low", "low"],
            ["medium", "medium"],
            ["high", "high"],
          ],
          config.codex.reasoning_effort,
        )}${field("ollama_model", "Установленная модель Ollama", config.ollama.model)}${field("temperature", "Температура Ollama", config.ollama.temperature, "number", 'min="0" max="1" step="0.1"')}</div><p class="form-hint">Ollama требует установленную локальную модель. PDF и фото требуют модель с поддержкой изображений. При ошибке другой провайдер автоматически не включается.</p>${Object.entries(
          {
            system: "Системный промпт",
            defensive: "Защитный промпт",
            extraction: "Правила извлечения",
            style: "Стиль ответа",
          },
        )
          .map(
            ([key, label]) =>
              `<label>${esc(label)}<textarea name="${key}" rows="5" required data-no-translate>${esc(config.prompts[key])}</textarea></label>`,
          )
          .join(
            "",
          )}<div class="form-grid">${field("max_pages", "Лимит страниц PDF", config.limits.max_pages, "number", 'min="1" max="10" required')}${field("max_text_chars", "Лимит символов документа", config.limits.max_text_chars, "number", 'min="1000" max="60000" required')}${field("timeout_seconds", "Время ожидания, секунд", config.limits.timeout_seconds, "number", 'min="10" max="90" required')}${field("max_output_chars", "Лимит символов ответа", config.limits.max_output_chars, "number", 'min="2000" max="50000" required')}</div><details><summary>Обязательные ограничения</summary><p>Доступ только владельцу; подтверждение обработки; инструменты отключены; строгий формат ответа; проверка чисел и цитат; результат требует проверки сотрудником.</p><pre class="reference-text" data-no-translate>${esc(info.guardrails)}</pre></details><h3>Предпросмотр оформления</h3><div id="ai-style-preview"></div><p class="form-error"></p><div class="actions"><button class="primary" type="submit">Сохранить настройки</button><button class="secondary" type="button" id="ai-export">Экспорт JSON</button><button class="secondary" type="button" id="ai-defaults">Загрузить базовые настройки</button></div><label>Импорт конфигурации<input id="ai-import" type="file" accept=".json,application/json"></label><p class="form-hint">Импорт и загрузка базовых настроек создают черновик. Нажмите «Сохранить настройки», чтобы применить его. Не добавляйте пароли и ключи в промпты.</p><small data-no-translate>Revision: ${esc(revision.slice(0, 12))}</small></form>`,
      );
      const form = $("#ai-settings-form");
      function read() {
        const values = Object.fromEntries(new FormData(form));
        return {
          schema_version: 1,
          enabled: form.elements.enabled.checked,
          provider: values.provider,
          display_mode: values.display_mode,
          codex: {
            model: values.codex_model.trim(),
            reasoning_effort: values.reasoning_effort,
          },
          ollama: {
            model: values.ollama_model.trim(),
            temperature: Number(values.temperature),
          },
          prompts: Object.fromEntries(
            ["system", "defensive", "extraction", "style"].map((k) => [
              k,
              values[k],
            ]),
          ),
          limits: Object.fromEntries(
            [
              "max_pages",
              "max_text_chars",
              "timeout_seconds",
              "max_output_chars",
            ].map((k) => [k, Number(values[k])]),
          ),
        };
      }
      const preview = () =>
        window.SurveyorAIText.render(
          $("#ai-style-preview"),
          "**INSON**\n- 0.5%\n- 100 000 000 UZS",
          form.elements.display_mode.value,
        );
      form.elements.display_mode.onchange = preview;
      preview();
      form.onsubmit = async (event) => {
        event.preventDefault();
        const button = form.querySelector('[type="submit"]');
        button.disabled = true;
        try {
          const saved = await api("/ai-pilot/settings", {
            method: "PUT",
            body: JSON.stringify({ revision, config: read() }),
          });
          revision = saved.revision;
          $("#modal").close();
          await window.SurveyorCodexPilot.page();
          toast("Настройки ИИ сохранены");
        } catch (err) {
          form.querySelector(".form-error").textContent = err.message;
        } finally {
          button.disabled = false;
        }
      };
      $("#ai-defaults").onclick = () =>
        render(
          info.defaults,
          "Черновик базовых настроек — сохраните для применения.",
        );
      $("#ai-export").onclick = () => {
        const url = URL.createObjectURL(
          new Blob([JSON.stringify(read(), null, 2)], {
            type: "application/json",
          }),
        );
        const link = document.createElement("a");
        link.href = url;
        link.download = "surveyor-ai-config.json";
        link.click();
        setTimeout(() => URL.revokeObjectURL(url), 1000);
      };
      $("#ai-import").onchange = async (event) => {
        try {
          const file = event.target.files[0];
          if (!file) return;
          if (file.size > 100000)
            throw new Error("Конфигурация слишком большая");
          const draft = JSON.parse(await file.text());
          if (
            draft.schema_version !== 1 ||
            !draft.prompts ||
            !draft.limits ||
            !draft.codex ||
            !draft.ollama
          )
            throw new Error("Неверный формат конфигурации");
          render(draft, "Черновик импортирован — сохраните для применения.");
        } catch (err) {
          form.querySelector(".form-error").textContent = err.message;
        }
      };
    }
    render(info.config);
  }
  return { open };
})();
