# Inspection assistant

The inspection now has an **Assistant / Помощник** step. Save basic inputs with **Save draft → assistant** to get questions and calculation context without prematurely confirming a report.

## Workflows

- **Guided questions:** code selects evidence questions and required photo views for the object type, class/template risk features and missing documents. Extracted-value conflicts create follow-up questions. Answers remain attributed human input and do not silently become calculation inputs.
- **Cross-document comparison:** select the inspection documents and consent to processing them together with the inspection context. The model compares the evidence and proposes findings, questions and explanations. Sources include named documents, inspection inputs, saved answers and the deterministic product/template/calculation/statistical context. Nonvisual citations require an exact quote from a supplied source; unknown sources and unsupported text quotes are discarded.

  The model receives only indicator observations selected by the deterministic calculation, with an explicit scope note and available/included counts. This prevents the full public catalogue from exhausting the document input budget. The complete context remains in the review snapshot and freshness fingerprint; omitted observations are not evidence for model claims.
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

### Live browser check, 2 October 2026

A visible Chromium session exercised the temporary public HTTPS app, its actual database/worker, and the signed-in Codex provider using fictional files. Telegram launch proof was generated locally for the configured owner; this does not establish native Telegram acceptance. The contract's ten fields matched the fictional original. Cross-document analysis identified conflicting insured sums without changing calculation inputs, and image analysis identified a contract scan without claiming physical property risks. Human acceptance/correction/rejection, saved guidance answers, mobile layouts, report creation, and PDF/Word downloads passed. Both downloaded formats contained the reviewed discrepancy and document provenance without raw bold markers.

This check exposed an input-budget failure with the populated public database: the request included about 218,000 characters, mostly unused statistics. Selecting calculation observations reduced the same request to about 9,900 characters, and the live comparison then completed. A regression test now covers a catalogue larger than the input limit while retaining the selected market observation and full review context. Assistant field labels and model finding categories were also localized. Validation after these changes: 270 Python tests and the browser workflow pass. Private live-test artifacts and fictional inspection records remain outside Git.
