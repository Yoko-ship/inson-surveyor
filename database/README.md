# Public database snapshot

[`public-data.sqlite`](public-data.sqlite) contains **12,808 public statistical observations** from CBU, SIAT and NAPP as collected on 2 October 2026. It is an ordinary SQLite file included in Git, so pulling this branch downloads the data on Windows, macOS and Linux. The companion [`public-data.json`](public-data.json) records the SHA-256 and per-channel counts.

The database was built from a fresh schema and contains only public channels and observations. Accounts, password hashes, sessions, Telegram identities, login attempts, audit logs, inspections, documents, reports, customer claims and approval identities are absent. Original company PDFs and local `.env` files remain private. This is a portable public-data snapshot, not a backup of anyone's working environment.

The normal local launcher imports missing observations automatically in synthetic mode:

```powershell
.\scripts\run_local.ps1
```

```sh
sh scripts/run_local.sh
```

To import explicitly into the database configured on the current computer:

```sh
uv run python scripts/public_database.py import
```

Import validates the checksum, SQLite integrity, allowed series and empty private tables first. It adds only missing series/periods; existing local values, corrections, approval identities, accounts, surveys and source configuration are preserved. Repeated imports are safe. Do not replace `data/surveyor.db` with this snapshot: use the importer, which also prepares the application schema. PostgreSQL targets are supported by the same importer.

To inspect or refresh the checked-in snapshot after collecting updated public data locally:

```sh
uv run python scripts/public_database.py check
uv run python scripts/public_database.py export
```

Export accepts only known official CBU/SIAT/NAPP series, strips local metadata and pricing approvals, and writes a fresh SQLite file. Commit both the `.sqlite` file and its `.json` manifest after validation. Public-source dates and limitations remain attached to the observations; NAPP reference data cannot change tariffs. No dataset refresh happens merely by pushing to GitHub.
