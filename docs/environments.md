# Environment profiles

## Local browser

`.env.example` documents configuration; `scripts/setup_local.py` creates `.env` only if absent. The actual file is ignored by Git and restricted to owner read/write (`0600`).

| Setting | Purpose |
|---|---|
| `TELEGRAM_BOT_TOKEN` | New bot's credential, never tracked or printed |
| `TELEGRAM_EXPECTED_BOT_ID` | Numeric identity checked before Telegram configuration changes |
| `TELEGRAM_WEBHOOK_SECRET` | Independent random credential validating incoming webhooks |
| `BOOTSTRAP_ADMIN_PASSWORD` | Generated initial password; first login requires changing it |
| `DATABASE_URL` | SQLite locally; PostgreSQL for permanent hosting |
| `STORAGE_DIR` | Private, backed-up upload directory |
| `PUBLIC_URL` | `http://localhost:8010` for ordinary local browser use |
| `COOKIE_SECURE` / `COOKIE_SAMESITE` | `false` / `lax` locally; `true` / `none` for Telegram HTTPS embedding |
| `DATA_MODE` / `HOSTING_COUNTRY` | Synthetic local testing; real data requires declared UZ hosting |

Run `sh scripts/run_local.sh`. Environment values already exported to the process take precedence over `.env` through Pydantic settings.

## Telegram development

Run `uv run python scripts/run_telegram_dev.py`. It reads the local `.env`, starts a Cloudflare Quick Tunnel and an app listener on `127.0.0.1:8012`, and supplies the HTTPS origin and secure cookie settings to that listener. These temporary overrides do not overwrite `.env`.

The runner uses `.env` values in preference to shell values for reproducibility. Only one runner may run at a time, enforced by a filesystem lock. Set `TELEGRAM_DEV_PORT` in `.env` if 8012 is occupied. Logs and the non-secret status JSON live in ignored `data/telegram-dev/`. The existing browser listener on 8010 can run independently against the same development database.

Cloudflare Quick Tunnels have temporary hostnames and stop when their process stops; they are a development facility, not permanent hosting. [Official documentation](https://developers.cloudflare.com/tunnel/get-started/quick-tunnels/).

## CI

GitHub Actions uses disposable SQLite/PostgreSQL data, synthetic bootstrap credentials and mocked Telegram calls. The Playwright runner explicitly clears `TELEGRAM_BOT_TOKEN`. No live bot credential or customer data is needed in Actions secrets. The protected branch requires code/security, PostgreSQL migration and browser workflow checks.

## Permanent hosting

The Docker/Compose/Railway files remain deployment scaffolding. Configure secrets directly on the chosen host, HTTPS, a stable `PUBLIC_URL`, secure cookies, persistent database/uploads and backups. `COOKIE_SAMESITE=none` without `COOKIE_SECURE=true` is rejected. Apply migrations before startup and configure Telegram only after public health succeeds.
