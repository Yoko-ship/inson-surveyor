# ТЗ and SWOT coverage

Source: the two user-supplied PDFs, dated 01.10.2026. Their descriptions of a previous system are requirements/evidence supplied by the user, not verification of an existing codebase. The workspace initially contained only those PDFs.

| Requirement | Implementation / acceptance boundary |
|---|---|
| 3.1 Upload → review → report | Browser workflow; own inspections; uploads; source review; required confirmation; frozen report; Word/PDF; explicit Telegram delivery |
| 3.2 Text vs scan | Rules for PDF/DOCX/XLSX/TXT/CSV; image/scan validation and manual path. AI deliberately excluded by user instruction |
| 3.2 Missing vs blank | Separate `unavailable`, `blank`, `needs_review`, `extracted` states; source excerpts retained |
| 3.2 Cross-source reconciliation | Report lists differing extracted values and employee-entered differences |
| 3.3 Annual/fixed | Exact ТЗ examples tested: 100m × 0.5% × 1095/365 = 1.5m; fixed = 500k |
| 3.3 Rate types | Annual/fixed/program/normative, selected program rate and explicit formula basis; no guessed statutory data |
| 3.3 Floor and comparison | Minimum floor, bounded adjustments, annualized market comparison and requested-premium discrepancy |
| 3.4 Valuation | Comparable eligibility within six calendar months; original-price median; explicit outlier rule; mean/range; 15% threshold; depreciation; appraiser plus independent sourced/date-stamped check |
| 3.5 Public data | CBU official API; daily worker/on demand; schema validation; refusal disables channel; cached values/dates; version history; stale indicators excluded from numerical rate changes |
| 3.6 Employees | Required identity and contact fields; unique login/phone/Telegram ID; minimum password length; forced change; roles and audit |
| 3.7 Products | Versioned effective dates; validated type/rate/minimum; XLSX/CSV row preview; atomic explicit confirmation; history preserved |
| 3.8 Claims | Product/year validation, nonnegative values, import confirmation; yearly ratios; three-year report context; actuarial-only bounded calibration |
| 4–5 Other external channels | All listed channels registered with explicit manual/review/contract status. Live adapters require verified permission and actual dataset schemas; none are fabricated |
| 5 Source provenance | Links, observation period/date and retrieval time, history, staleness, unapproved adjustment labels |
| SWOT: underwriter decisions | Append-only decisions, stale-report rejection, report remains subject to confirmation |
| SWOT: no AI dependency | Entire report flow works without model access |
| SWOT: secret handling | Ignored `.env`, restricted local permissions, no tokens in tracked source, secret scanner and CI |
| SWOT: three languages | Navigation and report headings RU/UZ/EN; source excerpts/clauses preserved. Full translated forms and legal text remain an acceptance item |
| SWOT: Uzbekistan hosting | Configuration guard for real-data mode; no hosting selected or cloud deployment performed per latest user instruction |
| SWOT: mobile Telegram | Responsive browser tested at mobile viewport; native Telegram HTTPS acceptance awaits hosting. Existing bot webhook left intact |

## Explicit implementation choices requiring insurer review

- Demo risk weights and multipliers are visible, versioned and labelled as unapproved. Default class templates cover vehicle, property and fire. Other classes can be added without code.
- Comparable outliers are prices outside 50–150% of the eligible-price median when at least three observations exist. This transparent initial rule is documented in reports and requires business calibration.
- Calibration uses total payouts / total premiums over three complete years, target ratio supplied by the actuary and a ±20% cap. This is a proposed deterministic policy, not an invented company tariff.
- Statutory product setup requires actual source URL, rate and annual/fixed basis. More complex ОСГОР formulas, if required by supplied normative materials, need an explicit validated rule rather than a generic guessed tariff.
- Legacy binary `.doc` and `.xls` must be converted to `.docx` and `.xlsx`; malformed, encrypted and macro-bearing uploads are rejected.

## Acceptance inputs still needed

Approved company products/tariffs, class rules, normative ОСГОР basis, representative contracts and branch requests, company loss history, qualified actuarial/underwriting accounts, approved source permissions and dataset schemas, complete translations, Uzbekistan production host and backup policy. These are not replaced with invented production values.
