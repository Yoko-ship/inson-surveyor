# AI configuration

AI configuration belongs to the codebase. The Mini App exposes document analysis only; it has no settings editor, configuration import/export, or settings API, including for administrators. Another coding assistant can change the version-controlled configuration through the normal code review workflow.

## Configuration files

- `surveyor/ai/defaults.json` is the authoritative runtime configuration: active provider, model options, system/defensive/extraction/style prompts, request limits, and display mode. Despite its filename, it is read directly for every request; there is no runtime override.
- `surveyor/ai/guardrails.txt` contains the mandatory application policy.
- `surveyor/ai_providers.py` implements the provider adapters and common output contract.
- `surveyor/static/ai_text.js` renders AI summaries safely.

Codex with the existing ChatGPT sign-in remains active, using medium reasoning, a 90-second timeout, 10 PDF pages, 60,000 input characters and 20,000 output characters. The configured style requests short professional prose in RU/UZ/EN; the renderer handles paired Markdown emphasis and lists if the model still produces them. Existing requests retain their configuration snapshot. If a code change updates settings while an upload form is open, the owner must refresh and reconfirm processing.

To update behavior, edit `surveyor/ai/defaults.json`, validate it and commit the change:

```sh
uv run python scripts/ai_config.py validate
uv run python scripts/ai_config.py show
uv run pytest tests/test_ai_config.py tests/test_codex_pilot.py tests/test_codex_telegram.py
```

Git provides configuration history and rollback. Backups include a validated `ai/config.json` and `ai/guardrails.txt` snapshot for provenance; restored snapshots do not automatically override the code. Legacy `data/ai/active.json`, its history, and the retired `AI_CONFIG_DIR` setting are ignored. Invalid code configuration stops AI inference rather than loading a fallback. Credentials remain in server-side secret configuration, never prompts or source control.

The optional Ollama adapter uses a locally installed model through `OLLAMA_BASE_URL` (default `http://127.0.0.1:11434`). Only HTTP loopback origins are accepted, without redirects or inherited HTTP proxies. Cloud-labelled/advertised remote models are rejected. PDF/image requests require vision support. Activating another provider requires a code configuration change; no model is downloaded and no provider fallback happens automatically. Ollama transport behavior is tested with mocks, so a chosen local model still needs live acceptance.

## Prompt and guardrail layers

1. Mandatory application policy establishes untrusted-document boundaries, no tools or side effects, source-grounded facts and human review.
2. Code-owned system and defensive prompts specialize behavior for INSON and Uzbekistan.
3. Code-owned extraction rules define units, dates, organization fields, missing values and ambiguity.
4. Code-owned style instructions request concise prose in the selected RU/UZ/EN interface language, without decorative Markdown.
5. Document text is sent separately as untrusted user content; it is never interpolated into trusted instructions. Codex receives app instructions through its developer-instructions configuration; Ollama receives a separate system message.

Prompts guide the model; code enforces access, CSRF, consent, a single inference at a time, input/page limits, timeouts, strict schemas, bounded output, secret-pattern checks and field validation. Codex tools remain disabled and unexpected tool events are rejected. Exact text quotes and supported numeric/date/name values are checked; image evidence still needs visual review. Summaries are model suggestions and are not independent verification. Nothing is automatically written into an inspection, tariff, reserve or approval.

Secret-pattern checks catch common key formats, not every form of personal or confidential information. Prompt defenses and schemas reduce risk; they cannot guarantee perfect resistance to prompt injection or factual errors. Follow [OpenAI's guidance on separating untrusted content and constrained outputs](https://developers.openai.com/api/docs/guides/agent-builder-safety).

## Provider contract and presentation

`surveyor/ai_providers.py` owns a registry of adapters with `status(config)` and `generate(config, instructions, content, images, directory, schema)`. Both existing adapters use the same app prompts and output contract. A new API provider needs its own transport/authentication adapter and configuration validation; credentials should stay in server-side secret configuration. Add adapter tests and run the same fixed samples before activating it. Changing providers does not imply identical quality or identical support for provider-specific settings.

The document result contains ten extracted fields plus a short summary. Each result carries its configuration revision and provider, which are also recorded in the audit event without document contents. [Codex developer instructions](https://learn.chatgpt.com/docs/config-file/config-reference) and [Ollama structured chat output](https://docs.ollama.com/api/chat) are the transport references.

`surveyor/static/ai_text.js` renders summaries with explicit DOM text nodes and a small formatting subset. `**bold**` becomes bold, paragraphs and lists receive normal spacing, and plain-text mode removes paired formatting markers. Model HTML is displayed as text and model links are not made clickable. Source quotations and extracted fields are kept verbatim rather than rewritten by the formatting layer.

## Inspection document review

The inspection workflow reuses this same code-owned configuration. `POST /api/ai-pilot/documents/{id}/analyze` creates a private persisted proposal after consent and revision checks; `GET .../{id}/proposal` resumes the latest pending proposal. `POST .../{id}/proposals/{proposal_id}/review` accepts only explicitly submitted fields, validates corrections, records all decisions and invalidates the inspection's final confirmation. All three endpoints retain the Telegram-owner restriction. Changed inspection versions require re-analysis.

Document evidence and immutable reports include the provider, configured model (or `provider_default`), configuration digest, file hash, source quote, original suggestion, decision, reviewed value, reviewer and timestamp. Rejected and unselected proposals never replace document values. Private proposal/review contents are retained in the operational database and backups, never the GitHub public snapshot. The standalone AI upload screen remains an unsaved preview.

The code-owned prompt set now also includes `inspection` and `photo` tasks. All transports use the same schema, secret-pattern, timeout, source-size and tool restrictions. Queued tasks record the configuration revision and stop before inference if it changes; the owner must consent again. Jobs use the shared source/image budget across selected files. The worker does not retain a database transaction during cloud processing. See [durable assistance](inspection-assistant.md).
