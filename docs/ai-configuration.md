# AI configuration

Open **AI → AI settings** in the Mini App. The configured Telegram owner can edit the system prompt, defensive prompt, extraction instructions, response style, provider/model, output presentation, and bounded request limits. Save applies to the next request without restarting. Existing requests keep their snapshot. If the configuration changes after an upload form was opened, the upload is rejected until the owner refreshes and confirms processing again.

Codex with the existing ChatGPT sign-in is the initial active provider. The optional Ollama adapter uses a locally installed model through `OLLAMA_BASE_URL` (default `http://127.0.0.1:11434`). Only HTTP loopback origins are accepted; no redirects or inherited HTTP proxies. Cloud-labelled/advertised remote Ollama models are rejected. PDF and image requests require a model advertising vision support. The app does not install/download models or fall back to another provider when one fails. Ollama compatibility is tested with mocked responses; a chosen local model needs live acceptance before use.

## Files, revisions and recovery

- `surveyor/ai/defaults.json`: initial provider-independent prompts, model options and limits, versioned in Git.
- `surveyor/ai/guardrails.txt`: mandatory application policy, versioned in Git.
- `data/ai/active.json`: validated local settings; survives app restarts and provider changes.
- `data/ai/history/<revision>.json`: previous and current configurations, addressed by SHA-256. Writes are atomic and serialized across processes; stale edits get HTTP 409.
- `AI_CONFIG_DIR`: optional alternative local configuration directory. Keep it outside public/static directories and version control. Current settings and history are included in the existing verified backup/restore workflow under `ai/`.

Export/import JSON from the settings screen to move prompts between machines or let another coding assistant edit them. Import and loading defaults populate a draft; **Save settings** applies it. Prompts must not contain credentials. Credentials and machine-specific addresses are deliberately excluded from exported JSON.

The CLI supports the same validation and revision check:

```sh
uv run python scripts/ai_config.py show
uv run python scripts/ai_config.py validate proposed-ai-config.json
uv run python scripts/ai_config.py apply proposed-ai-config.json --expected-revision <revision-from-show>
uv run python scripts/ai_config.py history
```

Apply an older history file with the current revision to roll back. Corrupt local JSON stops AI calls instead of silently replacing your prompts. To recover a corrupt file, preserve it separately, validate a known history/default JSON file, then replace `active.json` while the app is stopped. Restoring a full backup produces an `ai/` directory alongside the database and uploads; set `AI_CONFIG_DIR` to that restored directory when starting the restored app.

## Prompt and guardrail layers

1. Mandatory application policy establishes untrusted-document boundaries, no tools or side effects, source-grounded facts and human review.
2. Editable system and defensive prompts specialize behavior for INSON and Uzbekistan.
3. Editable extraction rules define units, dates, organization fields, missing values and ambiguity.
4. Editable style instructions request concise prose in the selected RU/UZ/EN interface language, without decorative Markdown.
5. Document text is sent separately as untrusted user content; it is never interpolated into trusted instructions. Codex receives app instructions through its developer-instructions configuration; Ollama receives a separate system message.

Prompts guide the model; code enforces access, CSRF, consent, a single inference at a time, input/page limits, timeouts, strict schemas, bounded output, secret-pattern checks and field validation. Codex tools remain disabled and unexpected tool events are rejected. Exact text quotes and supported numeric/date/name values are checked; image evidence still needs visual review. Summaries are model suggestions and are not independent verification. Nothing is automatically written into an inspection, tariff, reserve or approval.

Secret-pattern checks catch common key formats, not every form of personal or confidential information. Prompt defenses and schemas reduce risk; they cannot guarantee perfect resistance to prompt injection or factual errors. Follow [OpenAI's guidance on separating untrusted content and constrained outputs](https://developers.openai.com/api/docs/guides/agent-builder-safety).

## Provider contract and presentation

`surveyor/ai_providers.py` owns a registry of adapters with `status(config)` and `generate(config, instructions, content, images, directory, schema)`. Both existing adapters use the same app prompts and output contract. A new API provider needs its own transport/authentication adapter and configuration validation; credentials should stay in server-side secret configuration. Add adapter tests and run the same fixed samples before activating it. Changing providers does not imply identical quality or identical support for provider-specific settings.

The document result contains ten extracted fields plus a short summary. Each result carries its configuration revision and provider, which are also recorded in the audit event without document contents. [Codex developer instructions](https://learn.chatgpt.com/docs/config-file/config-reference) and [Ollama structured chat output](https://docs.ollama.com/api/chat) are the transport references.

`surveyor/static/ai_text.js` renders summaries with explicit DOM text nodes and a small formatting subset. `**bold**` becomes bold, paragraphs and lists receive normal spacing, and plain-text mode removes paired formatting markers. Model HTML is displayed as text and model links are not made clickable. Source quotations and extracted fields are kept verbatim rather than rewritten by the formatting layer.
