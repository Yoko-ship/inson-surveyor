# Сюрвейер

[Public repository](https://github.com/Yoko-ship/inson-surveyor) · [Telegram bot](https://t.me/analyzing12_bot)

Local-first insurance surveying platform implementing the deterministic workflows in the supplied ТЗ (01.10.2026). A browser application, Telegram Mini App integration, admin workspace and calculation engine share one Python backend. Financial calculations remain deterministic. An optional personal AI connection assists document extraction, with explicit human review before values are saved.

## Run locally

Requires Python 3.12+ and [uv](https://docs.astral.sh/uv/).

On Windows, run from PowerShell:

```powershell
.\scripts\run_local.ps1
```

If PowerShell blocks local scripts, use `powershell -ExecutionPolicy Bypass -File .\scripts\run_local.ps1` (only this process changes policy). The launcher accepts `uv` on PATH or the project-local `.tools/uv-package/bin/uv.exe`.

On macOS/Linux:

```sh
sh scripts/run_local.sh
```

Both launchers install the locked dependencies, preserve/create `.env`, apply migrations and start the browser app plus worker. With dependencies already installed, Windows can also run `.\.venv\Scripts\python.exe scripts/run_local.py` directly. No Docker, WSL, Node.js or Telegram credential is needed for browser use.

Open **http://localhost:8010**. Login: `admin`. The generated initial password is `BOOTSTRAP_ADMIN_PASSWORD` in the ignored `.env` file. Change it at first login. Changing this environment variable later does not reset an existing account.

The setup script preserves existing `.env` files and generates a random bootstrap password and webhook secret. Unix permissions are `0600`; on Windows, access follows the project folder's Windows permissions. Leave the Telegram fields empty for browser-only use. No default shared password is checked in.

The repository includes a [portable public database](database/README.md) with 12,808 CBU/SIAT/NAPP observations. The local launcher imports missing observations automatically in synthetic mode and preserves existing records. Accounts and private working data are not published.

Local SQLite data is in `data/surveyor.db`; documents are in `data/uploads/`. Restarting the app preserves both. Stop with Ctrl+C. Port 8010 avoids another application already using port 8000 on the development machine. Update both `PORT` and `PUBLIC_URL` if changing ports.

PDF export automatically finds Arial in the Windows fonts directory. `PDF_FONT_PATH` can override it, for example `C:/Windows/Fonts/arial.ttf`. Linux needs DejaVu Sans (already included in the Docker image).

## Workflows

- **Фото → Проверить → Акт:** upload text PDF/DOCX/XLSX/TXT/CSV or images; inspect rule-extracted fields with source excerpts; enter/correct values; confirm review; generate a five-section report; export Word/PDF.
- **Tariffs:** annual, fixed, program-based and statutory products; effective-date versions; minimum floor; annual equivalents for comparison; deterministic premium and document-discrepancy calculation.
- **Valuation:** dated comparable listings, original/edited prices, explicit outlier filtering, mean and minimum/maximum range in screen/Word/PDF, 15% deviation check, purchase less depreciation with a required purchase source/date, appraiser plus second method for large objects; CBU conversion when a current saved exchange rate exists.
- **Contract dates:** date-only documents suggest the actual date difference (end date excluded). The review form shows both dates and recalculates the term when they change. A different day-count convention requires an explanation; source discrepancies remain visible in the report.
- **Borrower:** optionally transcribe an organization's credit-bureau score, its scale and date, linked to a report uploaded to the same inspection. The evidence and score are frozen into the act without automatically changing the insurance tariff.
- **Market quotes:** Administration → Indicators accepts dated annual/fixed insurance quotes with comparable coverage, class, object type and region. Fixed quotes are annualized by their own term. Actual market offers must be supplied; NAPP aggregates are not treated as annual quotes.
- **Administration:** employee creation, unique login/phone/Telegram ID, forced first-password change, role management, versioned products and class templates, two-step Excel/CSV imports, claims by product/year, audit history.
- **Actuarial approval:** only the `actuary` role approves risk templates, public-data adjustments and loss-based calibration. Three complete calendar years and premiums are required. Editing claims invalidates the previous calibration automatically.
- **Underwriting:** only the `underwriter` role records approval, rejection or requested changes. Reports retain their original inputs, tariff version, source data and calculations after later edits.
- **Open data:** live CBU, eight SIAT feeds and NAPP insurance-class/reference workbooks; daily worker and on-demand collection; configurable permitted JSON/CSV/Excel/HTML sources; file preview/confirmation; versioned laws/notices; source history, stale dates, cached values and disablement on access/schema failures.
- **Document review:** correct each document or manually transcribe a scan with original values, reviewer and reason retained. Grouped millions are parsed without truncation; ambiguous separators, unsupported scales and ranges require review.
- **Source mapping:** the class-template screen shows linked statistics, missing observations and loaded metrics without rules. The rule editor suggests available metric names; the insurer still sets and approves baselines/sensitivity.
- **Operations:** local worker, daily verified SQLite/document backups, restore-to-new-directory command, source alerts and worker status. Source failures are isolated; maintenance runs independently, and transient collection errors retry in the next hourly cycle.
- **Telegram:** verified Mini App authorization, account linking inside Telegram, authenticated webhook, private `/start` and `/id` handling, explicit delivery of report PDFs to the signed-in employee's linked chat.

The calculator can use statutory products (including ОСГОР) once an administrator supplies the actual normative rate, formula basis and source. No statutory tariff is fabricated or seeded.

## Additional source references

**Тарифы и РНП** includes the supplied class-factor guide with search and class filters. Its coefficients are uncalibrated and do not alter pricing. **Sources** includes company/regional NAPP context with explicit accounting-geography limitations. OLX asking prices and confirmed E-auksion transactions can be entered as distinct valuation evidence; auction starting prices are excluded. See [resource integration and remaining inputs](docs/requirements.md#additional-resources-and-factor-reference--2-october-2026).

## Roles

| Role | Permission |
|---|---|
| Employee | Own inspections, uploads, reports and calculator |
| Underwriter | Read inspections and record underwriting decisions |
| Actuary | Read inspections; claims, sources and class templates; approve calibrations |
| Administrator | Employees, tariff versions, imports, sources, templates, audit |

Administrator privileges do not silently grant actuarial or underwriting approval authority. Assign those roles to separate accounts.

## Telegram

The new bot is **[@analyzing12_bot](https://t.me/analyzing12_bot)**. Its token lives only in the ignored local `.env`. `TELEGRAM_EXPECTED_BOT_ID` pins the intended bot identity before profile or webhook changes. The previous bot's deployment is separate.

```sh
uv run python -m surveyor.cli telegram-check
```

To run the Mini App **inside Telegram while developing locally**:

On Windows, after local setup:

```powershell
.\scripts\run_telegram_dev.ps1
```

On macOS/Linux:

```sh
uv run python scripts/install_cloudflared.py
uv run python scripts/run_telegram_dev.py
```

The installer verifies the official release checksum and stores the binary in ignored `.tools/`. The runner starts a second local listener on port 8012, shares the local database/uploads, opens a temporary HTTPS tunnel, configures the bot profile/commands/webhook/menu and verifies the settings. Open the bot, press **Start**, then **Открыть Сюрвейер**. Sign in using an employee account; link Telegram from **Мой профиль** to receive reports.

The ordinary browser app at port 8010 remains available. The Telegram listener uses Secure, HttpOnly, SameSite=None cookies for embedding. Its HTTPS URL/settings are supplied only to the development processes, so `.env` retains the localhost URL. The tunnel works only while the runner and this computer stay online; stopping it clears its own webhook without dropping pending updates. Temporary tunnels are restricted to synthetic data.

Runtime status and logs are in ignored `data/telegram-dev/`. No bot token is written to status output, logs, GitHub Actions or repository files. See [environment profiles](docs/environments.md).

### Personal Codex connection in Telegram

AI prompts, models, guardrails and response formatting are configured only in code (`surveyor/ai/defaults.json` and `surveyor/ai/guardrails.txt`). Users have no settings editor or configuration API. Git preserves the configuration across machines and provider changes. See [AI configuration and provider changes](docs/ai-configuration.md).

Sign into the installed Codex CLI with ChatGPT on the computer running the app. In the ignored `.env`, set `CODEX_TELEGRAM_ENABLED=true` and `CODEX_TELEGRAM_OWNER_ID` to your numeric Telegram ID. Link that same ID to your administrator account. Restart `scripts/run_telegram_dev.py`, then open the bot's Mini App and select **AI / ИИ**.

Only that administrator, with valid signed Telegram launch data, can use the subscription. No Codex credentials are copied into the Mini App or GitHub. Keep this computer and the runner online. Reopen the Mini App when its five-minute Telegram launch authorization expires.

The Codex screen accepts PDF (up to 10 pages), images, DOCX, XLSX, TXT and CSV, up to 15 MB and 60,000 text characters. Clicking **Analyze document** after checking the cloud-processing consent sends the selected document to OpenAI using your Codex allowance. All PDF pages are rendered, including scanned pages. Temporary files are removed after processing; only a consent/preview event is audited. Values and source quotes are previews for human review and are not automatically saved to inspections or used for pricing. Images cannot establish a property's market value. Shared employee access is not enabled.

Inside an inspection, upload a file under **Materials**, then select **AI · review document**. Consent sends that stored file to the configured provider. Select the proposed fields you have checked, correct any values, and save your review; unchecked suggestions are rejected. Pending proposals survive reopening the screen. On the inspection form, use **Reviewed document fields** to copy accepted values, check the full inspection, and save to generate its report. Existing inspection inputs are replaced only through that explicit copy action or your edits.

Reviewed evidence records the original suggestion and quote, accepted/corrected/rejected decision, reviewer, time, provider, configured model and configuration revision. It appears in the immutable report snapshot and screen/Word/PDF output. Unreviewed proposals never affect reports or calculations. A changed inspection revision or file fingerprint requires re-analysis. Private proposals remain in the operational database and backups; they are excluded from the GitHub public-data snapshot.

After permanent hosting is selected, set `PUBLIC_URL`, `COOKIE_SECURE=true`, `COOKIE_SAMESITE=none`, `APP_ENV=production`, `TELEGRAM_EXPECTED_BOT_ID` and `TELEGRAM_WEBHOOK_SECRET`, then configure the bot:

```sh
uv run python -m surveyor.cli telegram-configure
```

To intentionally move the pinned bot from an existing webhook, add `--replace-webhook`. The command verifies bot identity and public app health before changing the webhook, then reads back the webhook and menu. `telegram-profile` sets commands/name/description without changing a webhook.

For a bot without an existing webhook, `uv run python -m surveyor.cli poll` supports local `/start` and `/id`. It refuses to start while a webhook exists. No messages are sent as part of setup or token verification.

## Public data

```sh
uv run python -m surveyor.cli collect  # collect if the daily interval has elapsed
uv run python -m surveyor.cli worker   # hourly check, maximum one scheduled collection per day
```

Ordinary provenance links are stored without fetching them. Only explicitly configured collector URLs on allowlisted official domains are fetched, after access checks. Restricted/unverified channels use file and reference imports. See [the source review and acceptance matrix](docs/requirements.md). No anti-bot protections are bypassed.

## Verification

```sh
uv sync --frozen
uv run ruff check .
uv run ruff format --check .
uv run pytest
uv run alembic check
uv run pip-audit
uv run python scripts/check_secrets.py --history
npm ci
npx playwright install chromium
npm run test:e2e
```

Browser tests use a separate disposable `data/browser-test.db` and port 8011. They never change local admin credentials or send Telegram messages. Browser screenshots are written to ignored `artifacts/`.

## Deployment preparation

`Dockerfile`, `compose.yaml` (PostgreSQL + persistent document storage), `railway.toml` and GitHub CI are included. No cloud deployment is performed in this phase.

For Compose, add a strong URL-safe `POSTGRES_PASSWORD` to `.env`, then run `docker compose up --build`. Back up both the PostgreSQL database and the uploads volume. Do not use ephemeral filesystem storage for real documents. Run a single app instance until shared storage and distributed rate limiting are configured.

`sh scripts/run_local.sh` also starts the background worker. Administration → System status shows its heartbeat and backups. See [backup/restore commands](docs/operations.md).

`DATA_MODE=synthetic` is the local default. Demonstration products are explicitly labelled and are not company-approved rates. The ТЗ requires Uzbekistan hosting for real data: the app refuses `DATA_MODE=real` unless `HOSTING_COUNTRY=UZ`. This setting records an operator assertion; it cannot independently verify physical server location.

## Scope and acceptance

See [architecture](docs/architecture.md), [requirement coverage](docs/requirements.md) and [operations](docs/operations.md). Photos/scans support manual review and, for the configured Telegram owner, AI-assisted extraction. The interface and generated report sections support RU/UZ/EN; original source quotations and insurer-authored clauses remain verbatim, with per-language clause fields available. Actual tariffs, normative sources, company claims, approvals, restricted-provider access, production hosting and native Telegram acceptance remain external inputs/acceptance steps, not fabricated demo values.
