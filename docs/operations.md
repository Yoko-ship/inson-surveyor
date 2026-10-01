# Operations

## Local setup and credentials

Run `sh scripts/run_local.sh`. `.env` is intentionally untracked. Bootstrap credentials create the first admin only on an empty users table. Login and change that password, then create employees/underwriters/actuaries in Administration. All local data is synthetic by default.

Never commit `.env`, databases, uploaded client files or generated reports. Before any release run `uv run python scripts/check_secrets.py` after staging the intended files. The script reports filenames rather than secret values.

## GitHub configuration

CI checks Python lint/format, JavaScript syntax, calculation/workflow tests, migrations against SQLite and PostgreSQL, dependency vulnerabilities and tracked secrets. CODEOWNERS assigns the repository owner; Dependabot monitors Python, GitHub Actions and Docker dependencies. No deployment secrets are needed for local work.

Configured repository: [Yoko-ship/inson-surveyor](https://github.com/Yoko-ship/inson-surveyor), **public at the owner's request**, default branch `main`, squash-only merges, automatic merged-branch deletion, wiki disabled, read-only Actions token and vulnerability alerts enabled. Tracked files and reachable Git history were scanned for credentials before publication.

`main` requires pull requests with passing `checks`, `postgres`, and `browser` jobs and an up-to-date branch. Rules apply to administrators; force-pushes and deletion are disabled, and review conversations must be resolved. The single-maintainer setup requires zero additional approvals. GitHub secret scanning and secret push protection are enabled. Bot credentials stay in local `.env` or a future deployment's secret store, never in the public repository.

## Database changes

```sh
uv run alembic revision --autogenerate -m "Describe change"
uv run alembic upgrade head
uv run alembic check
```

Review generated migrations and test on a restored database before production. Never use runtime `create_all` for schema changes. PostgreSQL connection URLs use `postgresql+psycopg://`.

## Backups

For the single-process local app, stop writes, copy `data/surveyor.db` and the complete `data/uploads/` directory together, then resume. Preserve `.env` in a separate secure secret store. Restore to another local directory, run migrations, and verify a saved report and its source document before considering the backup usable.

For PostgreSQL use `pg_dump` plus a versioned snapshot of the uploads volume. Backups must follow the same location/access requirements as the live data. Test restore before real-data acceptance; no automated cloud backup is claimed by this local implementation.

## Source failures

Administration/Open data shows source errors and last successful fetch. CBU access refusal or schema drift disables automatic collection; transient HTTP failures preserve the cached dataset. Investigate adapter/schema/permission changes before re-enabling. Do not retry a blocked endpoint or change identities to bypass a denial.

## Telegram

The new bot is `@analyzing12_bot`. `scripts/run_telegram_dev.py` starts a temporary HTTPS tunnel and a secure second local listener. Ordinary local startup never changes a webhook. All provisioning checks `TELEGRAM_EXPECTED_BOT_ID`; moving an existing webhook requires the explicit configure flag. Graceful development shutdown only removes the webhook if it still points to that exact tunnel.

After a computer crash or lost tunnel, inspect the bot using `getWebhookInfo` before intentionally replacing its stale development URL. For permanent hosting, use the documented configure command. Compare `/health`, login, fresh Mini App signed authorization, report download and explicit send-to-self from a real phone. Browser verification does not establish native mobile Telegram acceptance.

## Production gates

HTTPS cookies; Uzbekistan hosting for real data as required by the supplied ТЗ; actual approved tariffs; reviewed statutory formulas; calibrated risk settings; non-demo accounts; persistent database/uploads; tested backups; protected logs; live source permission review; complete translations; real Telegram phone test. `HOSTING_COUNTRY` is an assertion, not an independent residency detector.

## Background work and restoration

`sh scripts/run_local.sh` starts the app and a single local worker. `uv run python scripts/run_worker.py` starts the worker independently when the app was launched another way. Its file lock prevents a second worker for the same data directory. The worker collects due channels hourly, performs daily collection per channel, expires old sessions/login buckets, and creates a verified daily SQLite backup when enabled. Administration → System status shows the heartbeat, backups and source errors. Source failures are also shown on their channel rows.

```sh
uv run python scripts/backup.py create
uv run python scripts/backup.py verify --backup data/backups/BACKUP_NAME
uv run python scripts/backup.py restore --backup data/backups/BACKUP_NAME --destination data/restored-review
```

The restore destination must not exist. The restored database is `database.sqlite`; document paths point to its restored uploads directory. It does not overwrite the running app, and existing sessions are removed. Verify the restored app with a separate database URL/port before intentionally switching environments. Backups contain confidential application data and password hashes: keep them in protected local storage; `.env` is excluded and must be protected separately.

Settings: `BACKUP_ENABLED=true`, `BACKUP_DIR=data/backups`, `BACKUP_RETENTION_DAYS=14`. This automated backup implementation is for the current SQLite local profile. PostgreSQL production backups still require the host's scheduled `pg_dump`/volume backup and restore acceptance described above.

## Source administration

Open data → Configure records an exact official HTTPS URL, permission evidence, refresh interval and column mappings. Formats: JSON, CSV, XLSX, HTML table, SIAT, NAPP or versioned text document. The JSON path and HTML table index are explicit mappings, not executable code. Redirected dataset endpoints are rejected for administrator review. A refused or schema-changed channel stays disabled until an administrator reviews it and explicitly re-enables/reconfigures it.

Upload file offers CSV/Excel preview and confirmation for every registered channel, including channels without automated access. Public reference material can be entered or read from a text PDF/Word/Excel file; scanned files require manual text entry. Select those materials during inspection review to freeze them into the report. Source updates do not rewrite past acts.

The current provider review is in `docs/source-access-review.json`. Permission for one provider/path does not authorize another. Do not turn on a restricted provider merely because its homepage opens.

## Telegram development updates

The temporary tunnel runner now watches the application Python directory and reloads the local Telegram listener when backend files change, preserving the current tunnel URL. Stopping the runner still removes only its own webhook. Static assets use no-cache responses. The regular local listener remains separate.
