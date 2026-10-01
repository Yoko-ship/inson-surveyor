# ТЗ implementation and acceptance

Source: “ИИ-сюрвейер — ТЗ логика системы”, 01.10.2026, sections 1–7. On 01.10.2026, after the audit, the user explicitly chose to leave AI recognition out for now. Permanent hosting remains unprovisioned. This document distinguishes implemented workflows from live provider coverage and insurer acceptance.

## Audit fixes completed on 1 October 2026

| Audit finding | Implemented correction | Remaining acceptance |
|---|---|---|
| Grouped amounts were truncated | Repeated comma/dot grouping and mixed decimal/grouping formats are parsed conservatively. Ambiguous single separators, numeric ranges and unsupported scales are marked for review | Validate against actual company documents |
| Contract dates did not inform duration | Date-only documents derive the actual date difference, including leap years; both dates appear in the form and report. The end date is excluded by default, visibly stated. An explicit differing duration needs a correction reason | Insurer confirms contract day-count conventions |
| CBU failures could stop collection and maintenance | Atomic collection claims, visible redacted errors, hourly retry for transient failures, per-channel isolation and independent maintenance. Refused/schema-changed sources remain disabled | Ongoing operation on the final host |
| Valuation range and purchase evidence were incomplete | Minimum/maximum range is rendered in all report formats. New equipment inputs require purchase source/date; legacy unsourced values remain unconfirmed | Real price evidence from the employee |
| Borrower block was absent | Organization, bureau, score, scoring scale, report date and employee review linked to an uploaded document owned by the same inspection; immutable report snapshot | Actual credit-bureau report; contractual API access remains separate |
| No convenient annual market-quote workflow | Dedicated annual/fixed quote form and API, actual term conversion, class/object/region scope, source/date/coverage evidence in reports | Supply valid comparable insurance offers; none are invented or seeded |
| Loaded statistics could be mistaken for configured adjustments | Class-template coverage view and available-metric suggestions. Calculations/reports explicitly identify missing linked regional data and missing annual market quotes | Insurer supplies baselines/sensitivity; actuary approves rules |

Verification: 136 automated tests passed; expanded browser acceptance passed, including contract dates, grouped amounts, borrower evidence, valuation range, fixed-quote annualization and mobile layout. Statement coverage was 84%. The local CBU recovery collected 74 exchange-rate observations. The changes do not convert demonstration tariffs into approved insurer policy.

## Implemented local workflows

| ТЗ | Implemented behavior | Verification |
|---|---|---|
| 3.1 Photos → review → report | File upload and classification; four primary inputs; effective tariff selection; regional/class context; discrepancy checks; class clauses; five sections shared by screen, Word and PDF; explicit Telegram PDF delivery | API workflow and browser tests |
| 3.2 Document processing | PDF/DOCX/XLSX/TXT/CSV rules; size/page/archive limits; missing/blank distinction; organization-only party extraction; photo/scan manual review; per-document corrections preserve original values, reviewer and reason; stale revision rejection | Parser and document-review tests |
| 3.3 Rates | Annual/fixed/program/statutory basis; Decimal premium; minimum floor; fixed-rate annual equivalent; risk levels; bounded public-data rules by object type; market comparison only when an annual quote is actually supplied | Calculation fixtures, including the exact three-year examples |
| 3.4 Valuation | Six-calendar-month comparable window; original-price median; configurable outlier bounds; mean/range; 15% default tolerance; purchase less depreciation; configurable large-object threshold requiring appraiser plus dated independent second method | Valuation and threshold tests |
| 3.5 Collection | Daily scheduled/on-demand collectors; official host allowlist; robots checks; request serialization across app/worker; bounded downloads; format validation; disable on refusal/schema drift; cached observations; immutable versions; dates, provenance and stale labels; administrator error screen | Parser, refusal, schema, region and history tests plus live collection |
| 3.6 Employees | Name, position, department, branch, login, password, phone and role; unique login/phone/Telegram identity; forced first-password change; role restrictions; account activation/deactivation; audit | Authentication and role tests |
| 3.7 Products | Four rate types; program rate editor; statutory source/basis; effective versions; validated CSV/Excel preview and atomic confirmation; historical reports preserve old versions | Product/import/calculation tests |
| 3.8 Claims | Product/year validation; preview/confirmation; yearly counts and payouts; loss ratio/frequency; three completed years in reports; actuarial calibration only; changed claims invalidate prior calibration | Claims/calibration tests |
| 4–5 Public sources | CBU; four SIAT datasets; NAPP official workbook; configurable JSON/CSV/XLSX/HTML-table collectors; versioned public-document monitoring; manual file/reference fallback; explicit permission/contract statuses | See source review below |
| 6 Failure behavior | Unknown stays unavailable; no statutory rate or annual market quote invented; prohibited sources stay disabled; last cached values retain observation dates; data changes preserve report snapshots | Failure/regression tests |
| 7 Local acceptance | Migrations, role workflows, generated reports, imports, mobile viewport, RU/UZ/EN interface paths, backup integrity and restore checks | Pytest, Playwright and GitHub CI |

## Live collectors

- CBU official exchange rates, with nominal normalization.
- SIAT 800: regional registered crimes (annual).
- SIAT 1244: housing area (annual, applicable to housing).
- SIAT 3251: published road-accident reporting periods (quarterly). Published cumulative periods are not summed together.
- SIAT 4690: regional consumer price indices against the previous month.
- NAPP: latest completed-quarter XLSX linked by the official publication index, sheet 1.4, 18 insurance classes, premiums/payments/liabilities in UZS and payout/premium ratios. Aggregate premiums divided by liabilities are **not** labelled an annual market tariff.

Live verification on 01.10.2026 collected 4,390 SIAT observations and 142 NAPP indicators in addition to CBU exchange rates. These are public statistics, not fabricated company experience. Importing a historic period cannot replace a more recent observation. Re-fetching unchanged data preserves actuarial approval; changed data creates an unapproved version.

## Source access review

[Machine-readable review](source-access-review.json) records checked endpoints and responses. Website reachability alone is not treated as permission or a validated dataset.

| Channel | Current path |
|---|---|
| CBU, SIAT, NAPP | Connected official downloads/APIs |
| Avtoelon | Written permission required by its published agreement; no automatic collector enabled |
| Meteo | API access application required; file/reference fallback until access is supplied |
| Seismos | Current site maintenance page; no validated event dataset available; manual sourced observations supported |
| UZEX | Quotation `/pages` paths fall under the published `/page` robots restriction; not scraped |
| Lex, construction, licenses, courts | Robots endpoints redirect or return HTML; automated collection remains disabled until access is verified; versioned manual references supported |
| E-auksion, egov, new-car prices, customs | Accessible sites; production dataset/format and applicable access terms still need verification. File import and configured permitted-feed adapters are implemented |
| OLX, uybor, joymee | Employee-provided files/comparables; no scraper |
| Credit bureau and government registries | Contract-dependent; uploaded credit-bureau reports have a dedicated borrower block; automated credentials/datasets not supplied |

## Configuration rather than invented insurer policy

Administrators can set program rates, annual/fixed statutory basis with a normative source, class thresholds, risk weights, risk shares, regional indicator baselines/sensitivity, bounded adjustments, valuation rules and translated clauses through forms. New template versions require fresh actuarial approval. Demo values remain explicitly unapproved.

The implemented calibration policy uses total payouts / total premiums for three completed years, an actuary-supplied target and a ±20% cap, further bounded by the class template. This policy and the default 50–150% median outlier rule are implementation choices requiring insurer approval before operational use.

## Deliberately deferred or externally dependent acceptance

- AI recognition and the AI specialist: excluded by the user's instruction. Scan/photo manual review works without a model.
- Permanent Uzbekistan hosting and real-data operations: not provisioned; current browser and temporary Telegram HTTPS testing run on the local Windows computer. A temporary tunnel does not satisfy permanent-hosting acceptance.
- Approved company tariffs, normative references, claims history, staff accounts and business-rule approval: the entry/import/approval workflows are built; the insurer must supply and approve its actual values.
- Restricted-provider credentials and permission: cannot be manufactured by implementation. The fallback/configuration workflows are built; those providers are not represented as live integrations.
- Native Telegram on a real phone: webhook/menu/HTTPS authentication and browser workflows are verified; human phone acceptance remains separate.
- Legal/editorial sign-off: interface and generated report labels support RU/UZ/EN. Original source quotations, organization names and insurer-authored clauses remain verbatim; translated clauses can be supplied per template.

A passing test suite verifies implemented behavior. It does not substitute for provider permission, insurer approval or real-phone acceptance.

## Public-data pilot preparation, 1 October 2026

The user has no company tariff sheet or product claims history and requested public-source research. The [research record](pilot-research.json) preserves source URLs, observations, document hashes and unresolved inputs. The [review workbook](../outputs/01a0f80b-caed-7bd2-a812-420edac31fd8/pilot-research.xlsx) summarizes the evidence and pilot steps. These are research artifacts; no live tariffs, claim rows or approvals were created from them.

- INSON's current property page links the My Home offer with four sum/premium pairs. The offer also states a minimum annual rate for custom sums. Confirm the current effective tariff, the package duration, eligibility and treatment of insurance classes 8/9 before configuring a pilot.
- The separate INSON complex-property offer uses component pricing. For its LITTLE program, the property premium plus liability premium is 175,000 UZS; applying its rounded 0.18% average to 100 million UZS would incorrectly give 180,000 UZS. Do not load this rounded average as an exact tariff.
- NAPP publishes INSON company-wide premiums, payouts and distinct received/paid/refused/unsettled claim counts for 2023-2025. Product allocations remain unavailable from the sources reviewed. Company-wide totals are not eligible for this application's product-level calibration.
- IMKON and EUROASIA publish annual KASKO reference rates. Their coverage and eligibility differ; they are not an approved set of comparable quotes. No average or automated adjustment has been created.

Next external input: an insurer contact to confirm the pilot tariff and supply product-level claims and approved rules. Provider credentials, Uzbekistan hosting and native phone acceptance remain separate dependencies. AI recognition remains excluded.

### Supplied company policy — 1 October 2026

The user supplied INSON's Appendix 1 to order 54-П dated 23 September 2025. The application now includes all 179 source rows (176 named products and three blank slots) in `surveyor/policies/inson-2025-09-23.json`. All 19 content pages were visually reviewed, including continuation rows; page 20 is blank. Russian names are concise catalogue labels, not substituted contract wording. Leading zeros, individual/company and vehicle variants, component minima, commission caps, source pages and the PDF SHA-256 are retained.

The **Тарифы и РНП** screen is available to authenticated employees. It supports search, document-level rate/commission checks, component checks and access to the installed original PDF. This reference catalogue does not seed active quote rates. An administrator can configure a version from a supported row with a chosen rate, effective date, basis/terms references and confirmation of current applicability. Programme rows require programme rates, head-office rows require an approval reference, and compulsory products require a normative source. Manual creation and CSV/Excel previews enforce the same rules. The document date is not assumed to be an effective date; unspecified percentage rates are not assumed to be annual. Cargo 0701/0703 and explicitly fixed 0116/1426/1428 disallow annual prorating. Component products remain available for per-component checks; a single executable rate cannot replace their separate sums and terms.

Source ambiguities remain visible: 1304 prints `0,5` without a percentage sign; 1411's commission cell is partly struck through. Neither value is silently inferred. Blank slots 1318/1420/1422 remain non-executable. Product verticals are preserved separately from the legal class of each coverage; for example, 0815 explicitly mentions class 9 despite its 08 prefix. Avtolimit 0319 uses a limit as its amount basis.

RNP classification follows paragraph 10 of [regulation 1882](https://lex.uz/docs/1416860), checked on 1 October 2026. It covers classes 1–17, the class-13 borrower-liability and class-16 crop exceptions, open dates, and proportional/nonproportional reinsurance. Missing subtype information yields an unresolved result. Nonproportional reinsurance combined with open dates is referred for clarification. Paragraph 11 requires separate treatment of parts belonging to different groups. Classification can be saved for a coverage in a survey and appears in the immutable report/export with its rule version. No reserve amount, refund amount, risk score or pricing factor is inferred from a group.

Still needed for operational pricing: confirmation of policy applicability, referenced programmes/master agreements, product-specific claims and approved underwriting/risk rules. The original reference PDF is local protected storage, not a public repository asset. Install it on another host with `python scripts/install_tariff_policy.py <source.pdf>`; the installer checks the catalogue hash. No database migration or new environment variable is required for the tariff policy feature.

### Personal Codex pilot — 1 October 2026

The user subsequently requested a Codex connection and explicitly selected **personal local testing with sample documents**, acknowledging cloud processing. A separate administrator screen now runs three built-in fictional samples through the installed Codex CLI using its existing ChatGPT sign-in. It accepts only a sample identifier, never an uploaded document, document path, custom prompt, company data or survey ID. Text, an actual rendered image (without its transcript in the model request), and missing fields are covered. The response has a strict schema and is compared against the known sample values and source quotes. A percent/fraction error is reported as a mismatch. Every output remains a suggestion; no result is applied to an inspection, tariff, reserve or report. Only the sample ID and match counts enter the audit log.

Enable locally with `CODEX_LOCAL_PILOT=true` (default false); `CODEX_CLI_PATH` is optional when desktop/CLI discovery works. The connection requires administrator authentication and CSRF protection, development mode, synthetic data, a localhost public URL and a loopback client/Host. Forwarded/tunnel requests are rejected. The Telegram deployment remains excluded even if the flag is inherited. `/health` separately reports `codex_local_pilot`; `ai_enabled=false` continues to describe recognition of inspection documents.

The adapter uses an ephemeral read-only Codex run in a temporary directory, ignores user configuration, disables shell/connector/plugin/hook/browser/computer/subagent capabilities, supplies no application secrets and never copies or reads cached credentials. Codex manages its own sign-in and account usage. Requests are serialized within the local process and time out after two minutes. No live model calls are made by automated tests.

Three live sample requests passed all 30 expected field comparisons on the installed Codex CLI 0.158.0-alpha.2.1. This small synthetic check is not real-document acceptance. The original requirement to process real documents on the company's own server remains unresolved; local Codex execution still uses cloud inference. Shared/commercial rollout needs a separate supported authentication arrangement; see [Codex authentication guidance](https://learn.chatgpt.com/docs/app-server#auth-endpoints) and [Sign in with ChatGPT](https://developers.openai.com/siwc/request-client-id).
