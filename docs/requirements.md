# ТЗ implementation and acceptance

Source: “ИИ-сюрвейер — ТЗ логика системы”, 01.10.2026, sections 1–7. The user's subsequent instructions exclude AI and defer permanent hosting. The SWOT is supporting context, not evidence that the previous bot's implementation was available.

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
| Credit bureau and government registries | Contract-dependent; employee-provided reference documents supported; credentials/datasets not supplied |

## Configuration rather than invented insurer policy

Administrators can set program rates, annual/fixed statutory basis with a normative source, class thresholds, risk weights, risk shares, regional indicator baselines/sensitivity, bounded adjustments, valuation rules and translated clauses through forms. New template versions require fresh actuarial approval. Demo values remain explicitly unapproved.

The implemented calibration policy uses total payouts / total premiums for three completed years, an actuary-supplied target and a ±20% cap, further bounded by the class template. This policy and the default 50–150% median outlier rule are implementation choices requiring insurer approval before operational use.

## Deliberately deferred or externally dependent acceptance

- AI recognition and the AI specialist: excluded by the user's instruction. Scan/photo manual review works without a model.
- Permanent Uzbekistan hosting and real-data operations: deferred by the user; temporary Telegram HTTPS testing runs on the Mac.
- Approved company tariffs, normative references, claims history, staff accounts and business-rule approval: the entry/import/approval workflows are built; the insurer must supply and approve its actual values.
- Restricted-provider credentials and permission: cannot be manufactured by implementation. The fallback/configuration workflows are built; those providers are not represented as live integrations.
- Native Telegram on a real phone: webhook/menu/HTTPS authentication and browser workflows are verified; human phone acceptance remains separate.
- Legal/editorial sign-off: interface and generated report labels support RU/UZ/EN. Original source quotations, organization names and insurer-authored clauses remain verbatim; translated clauses can be supplied per template.

A passing test suite verifies implemented behavior. It does not substitute for provider permission, insurer approval or real-phone acceptance.
