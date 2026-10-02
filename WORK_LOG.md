# Work log

This file records work in progress, implementation changes, verification results and remaining work. Entries describe completed actions separately from plans. Never record credentials, customer documents or private account details here.

## 2026-10-02 — Full factor-based tariff workflow

### Request and scope

Implement the outstanding workflow on page 11 of the supplied tariff-factor PDF: class/subgroup factors, numerical coefficients, multiplicative pricing with a minimum floor, unanswered-factor clarification, actuarial approval and statistical recalibration. Keep a running record of changes in this file.

### Completed

- Re-read the PDF and compared it with the implementation. The initial 139-row catalogue was reference-only; this work closes the factor-pricing and factor-level calibration gaps.
- Inspected calculation, class-template, inspection, report and claims storage. Existing templates and inspection inputs use versioned JSON; historic reports contain immutable snapshots.
- Created this log and repository instructions to maintain it during subsequent work.

- Added versioned factor policies and evidence-backed inspection answers, with validation of class membership, coefficient direction and numerical bounds.
- Added multiplicative factor pricing, minimum floor, statutory-rate protection and explicit exclusion of legacy risk/region/loss multipliers in factor mode.
- Added report snapshots/export text for factor selections, coefficients, approval, source page/hash and outstanding clarifications. Historical snapshots remain unchanged.
- Added 40 prose-listed factors omitted from the original 139 table rows (179 total configurable factors across the catalogue).
- Added private CSV/XLSX segmented experience preview/confirmation, statistical proposals and invalidation when the confirmed dataset changes. Reuses versioned JSON storage; no schema migration.
- Added factor administration, inspection and calculator UI, with RU/UZ/EN labels.

### Current status

- Implementation and validation complete. Code is pushed to PR #10; the final follow-up commit records this delivery result. External insurer inputs remain listed below.

### Verification

- First focused test command referenced a nonexistent test filename; collection stopped without running tests. Corrected the command.
- Focused factor/pricing/resource suite: 88 tests passed.
- First full regression run: 308 tests passed.
- Background browser acceptance passed: configure coefficients, import fictional CSV, calculate a statistical proposal, sign in as a separate actuary, approve, select inspection evidence, verify exact 600,000 UZS premium, mobile layout, PDF and Word downloads.
- Public snapshot integrity check passed (12,808 public observations); no private experience was exported.
- Added AI guidance for missing factors; the model receives calibration estimates and hashes while raw segmented experience remains in the saved review context.

- Added RU/UZ/EN labels, standalone calculator selections, and regression coverage for large AI calibration context, XLSX import, 3–5-year windows and successful underwriting approval.

- The large-context regression detected shared calibration references causing the omitted-row count to be overwritten from 1,000 to 0. Fixed the trimming operation to run only when raw rows are present; original saved context remains intact.
- Extended headless acceptance to the standalone calculator and English/Uzbek factor labels.

- Final Python regression suite: 317 passed (24.27 seconds). Ruff lint/format, JavaScript syntax, Prettier, diff checks, public database integrity, migration consistency and tracked/history secret scan passed.
- Extended browser test found that language switching discarded calculator inputs and selected factors by returning to the first product. Added in-memory calculator draft preservation across navigation/language changes, reset on authentication; browser retest passed.

- Final headless browser acceptance passed again, including exact calculator pricing, retained inputs/evidence after language changes, English/Uzbek labels, mobile layout, actuarial workflow and PDF/Word exports. No visible browser was opened.
- Local API reloads the new implementation. Refreshed the separate AI worker gracefully after confirming no queued/running jobs, so explanation jobs also use the new factor context.


- Final page-by-page source review found six further class-9 prose factors under “Прочие факторы” (a different heading from “Прочие”). Included all six: the complete configurable catalogue now has 179 entries (139 table rows + 40 prose factors). Added a source-text consistency regression.

- Exposed stable factor codes alongside labels in administration and inline CSV guidance. The import guide is readable inside Telegram without relying on an iframe-blocked attachment download.

- Added a validation guard against assigning another legal class to a numbered class template; covered both factor-policy and generic template endpoints. All affected pricing/assistant tests passed. Final browser run passed (13.7 seconds).


### Delivery

- Implementation committed and pushed as `1c46f17` on `codex/tariff-policy-local-codex`.
- Updated [PR #10](https://github.com/Yoko-ship/inson-surveyor/pull/10) with factor workflow, validation and remaining operational dependencies.
- [GitHub CI run 36999727254](https://github.com/Yoko-ship/inson-surveyor/actions/runs/36999727254) passed all five jobs: checks, Windows, PostgreSQL, browser and container. This validates implementation commit `1c46f17`; the delivery follow-up changes only this log.
- Local API health reports OK with AI enabled; the refreshed AI worker heartbeat is current.


### External inputs

- The PDF supplies directions of influence, not numerical coefficients or an approved statistical method. Operational coefficients, representative factor-segmented experience and actuarial approval must come from the insurer. Only fictional data was used for validation.
- Existing local templates were not switched or assigned invented coefficients. Configure a new factor version in Admin → Class templates → Configure factors, then obtain actuarial approval.
- Permanent hosting, restricted-provider integrations, native Telegram client acceptance and real-document validation retain their previous status; this change does not claim those are complete.

## 2026-10-02 — Public document search

- User requested an internet search for documents to help close validation/calibration dependencies.
- Searching official insurer/regulator sources for policy wording, contracts, claim/inspection forms and published experience. Checking applicability separately from availability; no operational tariff, coefficient or approval will be imported from search results.
- Existing public-research records are being checked to avoid presenting previously found company-wide totals as factor-segmented experience.

### Completed research and verification

- Recorded six accessible primary-source documents/references in `docs/public-document-research-2026-10-02.json`: INSON property wording/application, Uzbek My Home wording, voluntary motor liability wording, construction-risk wording, CASdatasets motor experience documentation and CAS Basic Ratemaking.
- Opened the four INSON PDFs and the two actuarial reference pages. Confirmed a blank property application on PDF page 17 through extracted text. A web PDF screenshot request failed; no visual table verification is claimed.
- Construction wording is hosted on INSON's `apitestsite` subdomain; current production applicability remains unverified. Public wording and blank forms are candidates for extraction tests, not completed client-case validation.
- French motor experience can support method benchmarking, but cannot establish INSON coefficients or be inserted into the current recent-year paid-loss calibration workflow without resolving incompatible fields and semantics.
- No suitable public INSON factor-segmented claims history or completed inspection/valuation corpus was established. Insurer experience and actuarial approval remain dependencies.
- No AI processing, private-document retrieval, database imports or operational pricing changes were performed.
