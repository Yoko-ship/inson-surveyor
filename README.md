# Сюрвейер

Local-first insurance surveying platform implementing the deterministic workflows in the supplied ТЗ (01.10.2026). A browser application, Telegram Mini App integration, admin workspace and calculation engine share one Python backend. **No AI provider, AI API calls or AI credentials are used.**

## Run locally

Requires Python 3.12+ and [uv](https://docs.astral.sh/uv/).

```sh
sh scripts/run_local.sh
```

Open **http://localhost:8010**. Login: `admin`. The generated initial password is `BOOTSTRAP_ADMIN_PASSWORD` in the ignored `.env` file. Change it at first login. Changing this environment variable later does not reset an existing account.

The setup script preserves existing `.env` files, generates a random bootstrap password and webhook secret, and sets file permissions to `0600`. The supplied Telegram token is configured locally; it is not included in Git. No default shared password is checked in.

Local SQLite data is in `data/surveyor.db`; documents are in `data/uploads/`. Restarting the app preserves both. Stop with Ctrl+C. Port 8010 avoids another application already using port 8000 on the development machine. Update both `PORT` and `PUBLIC_URL` if changing ports.

## Workflows

- **Фото → Проверить → Акт:** upload text PDF/DOCX/XLSX/TXT/CSV or images; inspect rule-extracted fields with source excerpts; enter/correct values; confirm review; generate a five-section report; export Word/PDF.
- **Tariffs:** annual, fixed, program-based and statutory products; effective-date versions; minimum floor; annual equivalents for comparison; deterministic premium and document-discrepancy calculation.
- **Valuation:** dated comparable listings, original/edited prices, explicit outlier filtering, mean/range, 15% deviation check, purchase less depreciation, appraiser plus second method for large objects; CBU conversion when a current saved exchange rate exists.
- **Administration:** employee creation, unique login/phone/Telegram ID, forced first-password change, role management, versioned products and class templates, two-step Excel/CSV imports, claims by product/year, audit history.
- **Actuarial approval:** only the `actuary` role approves risk templates, public-data adjustments and loss-based calibration. Three complete calendar years and premiums are required. Editing claims invalidates the previous calibration automatically.
- **Underwriting:** only the `underwriter` role records approval, rejection or requested changes. Reports retain their original inputs, tariff version, source data and calculations after later edits.
- **Open data:** official CBU currency adapter; daily worker and on-demand collection; source registry and manual indicator entry for other channels; version history, stale dates, latest cached values, failure notices and automatic disablement on access refusal/schema drift.
- **Telegram:** verified Mini App authorization, account linking inside Telegram, authenticated webhook, private `/start` and `/id` handling, explicit delivery of report PDFs to the signed-in employee's linked chat.

The calculator can use statutory products (including ОСГОР) once an administrator supplies the actual normative rate, formula basis and source. No statutory tariff is fabricated or seeded.

## Roles

| Role | Permission |
|---|---|
| Employee | Own inspections, uploads, reports and calculator |
| Underwriter | Read inspections and record underwriting decisions |
| Actuary | Read inspections; claims, sources and class templates; approve calibrations |
| Administrator | Employees, tariff versions, imports, sources, templates, audit |

Administrator privileges do not silently grant actuarial or underwriting approval authority. Assign those roles to separate accounts.

## Telegram

The supplied bot token was verified as `@inson_surveyor_bot`. It already has a webhook configured elsewhere. This project **does not replace it automatically**.

```sh
uv run python -m surveyor.cli telegram-check
```

The browser app works on localhost. A real Telegram Mini App needs an HTTPS address. After hosting is selected, set `PUBLIC_URL`, `COOKIE_SECURE=true`, `APP_ENV=production` and `TELEGRAM_WEBHOOK_SECRET`, then intentionally configure the bot:

```sh
uv run python -m surveyor.cli telegram-configure
```

For a bot without an existing webhook, `uv run python -m surveyor.cli poll` supports local `/start` and `/id`. It refuses to start while a webhook exists. No messages are sent as part of setup or token verification.

## Public data

```sh
uv run python -m surveyor.cli collect  # collect if the daily interval has elapsed
uv run python -m surveyor.cli worker   # hourly check, maximum one scheduled collection per day
```

The CBU adapter only calls its fixed official endpoint. User-supplied source URLs are stored as provenance and never fetched. Other sources remain manual, pending permission/format review, or contract-only as specified in the ТЗ. No anti-bot protections are bypassed.

## Verification

```sh
uv sync --frozen
uv run ruff check .
uv run ruff format --check .
uv run pytest
uv run alembic check
uv run pip-audit
npm ci
npx playwright install chromium
npm run test:e2e
```

Browser tests use a separate disposable `data/browser-test.db` and port 8011. They never change local admin credentials or send Telegram messages. Browser screenshots are written to ignored `artifacts/`.

## Deployment preparation

`Dockerfile`, `compose.yaml` (PostgreSQL + persistent document storage), `railway.toml` and GitHub CI are included. No cloud deployment is performed in this phase.

For Compose, add a strong URL-safe `POSTGRES_PASSWORD` to `.env`, then run `docker compose up --build`. Back up both the PostgreSQL database and the uploads volume. Do not use ephemeral filesystem storage for real documents. Run a single app instance until shared storage and distributed rate limiting are configured.

`DATA_MODE=synthetic` is the local default. Demonstration products are explicitly labelled and are not company-approved rates. The ТЗ requires Uzbekistan hosting for real data: the app refuses `DATA_MODE=real` unless `HOSTING_COUNTRY=UZ`. This setting records an operator assertion; it cannot independently verify physical server location.

## Scope and acceptance

See [architecture](docs/architecture.md), [requirement coverage](docs/requirements.md) and [operations](docs/operations.md). Photos/scans require human entry while AI is disabled. Source content, clauses and some form labels remain in Russian; Uzbek/English navigation and report headings are available, but full legal translations need review. Real tariffs, normative formulas, actual company claims, production hosting and mobile Telegram acceptance require the insurer's inputs.
