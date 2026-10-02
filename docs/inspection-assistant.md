# Inspection assistant

The inspection now has an **Assistant / Помощник** step. Save basic inputs with **Save draft → assistant** to get questions and calculation context without prematurely confirming a report.

## Workflows

- **Guided questions:** code selects evidence questions and required photo views for the object type, class/template risk features and missing documents. Extracted-value conflicts create follow-up questions. Answers remain attributed human input and do not silently become calculation inputs.
- **Cross-document comparison:** select the inspection documents and consent to processing them together with the inspection context. The model compares the evidence and proposes findings, questions and explanations. Sources include named documents, inspection inputs, saved answers and the deterministic product/template/calculation/statistical context. Nonvisual citations require an exact quote from a supplied source; unknown sources and unsupported text quotes are discarded.
- **Photo review:** select photographs to request visible-condition observations. Photos cannot establish hidden defects, structural safety, functioning protection, identity or market value. Photo observations have an explicit visual-review marker; a source ID is not proof of model accuracy.
- **Underwriting explanation:** the screen exposes exact values, formula and versioned tariff context from the calculation engine. Optional model explanations cite that supplied context; they cannot set financial values or approve coverage. Reference-only regional head-office statistics remain reference-only. Missing policy confirmation prompts a follow-up rather than being treated as approval.
- **Human review:** select and correct observations, record a review reason and confirm checking the originals. Unselected observations are rejected. The review increments the inspection revision and clears final confirmation. Saved reports retain original suggestions, corrections/rejections, quotes, source fingerprints, reviewer/time, configured provider/model and configuration revision. Changed inspection facts or tariff/statistical context marks previous reviews stale.

## Durable jobs

`AIJob` stores job state, consent/configuration revision, selected document IDs, attempts, retry time, lease and result. Supported tasks are `document`, `inspection` and `photo`. All enqueue/read/review endpoints require the configured linked Telegram owner and fresh signed launch data. Authorization for the queued work is recorded at enqueue; the worker rechecks active ownership and configuration before starting. An expired browser launch does not cancel a previously authorized job.

`scripts/run_ai_worker.py` runs independently of HTTP requests and browser connections. Local and Telegram launchers start it; Compose includes a separate restarting AI service. Its status heartbeat is exposed without secrets. One active job per inspection prevents accidental duplicates; identical enqueue retries return the existing job. Compare-and-swap leases recover interrupted jobs after 180 seconds, up to three attempts. Processing closes database transactions during cloud inference. Cancelled or superseded leases cannot publish results; document proposals and successful job completion commit atomically.

Provider failure schedules a bounded retry. Configuration, ownership and inspection changes stop the job and require a new explicit request. A crash after submission can lead to repeated inference: exactly-once cloud usage is not guaranteed. Closing Telegram is safe; the worker machine still has to stay online. Hosting is prepared separately in [deploy/README.md](../deploy/README.md), with provisioning deferred by the user.

The synchronous standalone upload preview remains available. Ordinary inspection document extraction uses the durable queue and resumes its persisted proposal on reopening. AI settings stay in code; no configuration controls were added to the Mini App.

## Validation

Run `uv run pytest` and `npm run test:e2e`. Coverage includes source/owner isolation, consent, configuration changes, stale facts and tariff context, interrupted leases, retries, cancellation, document proposal publication, corrected observations, questions, immutable reports and exports. Browser coverage simulates provider responses while exercising navigation away/back, saved answers, draft inputs, review controls and mobile rendering.

`uv run python scripts/evaluate_assistant.py --live` uses only built-in fictional documents and the existing configured sign-in. It checks contradictory amounts with an injected instruction and a contract scan presented to the photo task. On 2 October 2026 both cases passed with Codex CLI 0.160.0: comparison produced three cited findings without changing inputs; the scan produced an evidence finding and a follow-up question with no property-risk inference. These are bounded smoke checks, not evidence of real-document accuracy or perfect prompt-injection resistance. The user chose fictional validation; real-document and native-phone acceptance remain outstanding.

Migration `483bbb0a63a7` adds private job state and inspection assistance. The public GitHub snapshot has been rebuilt against that schema with the same 12,808 public observations; new private tables remain empty. Existing operational data survives the migration.
