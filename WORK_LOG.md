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

### In progress

- Commit/push the verified implementation and check GitHub CI.

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

- Final Python regression suite after the source audit: 316 passed. Ruff lint/format, JavaScript syntax, Prettier, diff checks, public database integrity, migration consistency and tracked/history secret scan passed.
- Extended browser test found that language switching discarded calculator inputs and selected factors by returning to the first product. Added in-memory calculator draft preservation across navigation/language changes, reset on authentication; browser retest passed.

- Final headless browser acceptance passed again, including exact calculator pricing, retained inputs/evidence after language changes, English/Uzbek labels, mobile layout, actuarial workflow and PDF/Word exports. No visible browser was opened.
- Local API reloads the new implementation. Refreshed the separate AI worker gracefully after confirming no queued/running jobs, so explanation jobs also use the new factor context.

### External inputs

- The PDF supplies directions of influence, not numerical coefficients or an approved statistical method. Operational coefficients, representative factor-segmented experience and actuarial approval must come from the insurer. Only fictional data was used for validation.
- Existing local templates were not switched or assigned invented coefficients. Configure a new factor version in Admin → Class templates → Configure factors, then obtain actuarial approval.
- Permanent hosting, restricted-provider integrations, native Telegram client acceptance and real-document validation retain their previous status; this change does not claim those are complete.

- Final page-by-page source review found six further class-9 prose factors under “Прочие факторы” (a different heading from “Прочие”). Included all six: the complete configurable catalogue now has 179 entries (139 table rows + 40 prose factors). Added a source-text consistency regression.

- Exposed stable factor codes alongside labels in administration and inline CSV guidance. The import guide is readable inside Telegram without relying on an iframe-blocked attachment download.

- Added a validation guard against assigning another legal class to a numbered class template; covered both factor-policy and generic template endpoints. All affected pricing/assistant tests passed. Final browser run passed (13.7 seconds).
