# Always-on deployment

Prepared for an owner-operated Linux server; no host has been provisioned. Real client data requires the project's Uzbekistan hosting profile. Use fictional files until hosting and insurer acceptance are settled.

## Start

1. Point a domain's DNS at the chosen server and permit TCP 80/443. Install Docker Engine with Compose, then check out this repository.
2. Create a protected `.env` from `.env.example` on the server. Set `POSTGRES_PASSWORD`, a fresh bootstrap password, `APP_DOMAIN`, `PUBLIC_URL=https://YOUR_DOMAIN`, `APP_ENV=production`, `COOKIE_SECURE=true`, `COOKIE_SAMESITE=none`, `DATA_MODE=synthetic`, the pinned Telegram bot credentials, `CODEX_TELEGRAM_ENABLED=true` and the owner's numeric Telegram ID. For real data, verify the host's location before setting `DATA_MODE=real` and `HOSTING_COUNTRY=UZ`.
3. Run `docker compose -f compose.yaml -f deploy/compose.https.yaml up -d --build`. PostgreSQL, uploads, Codex authentication and HTTPS certificates use persistent volumes; the app, source worker and AI worker restart independently. The database has no published port; the direct application port is bound only to loopback.
4. Sign into the server's Codex client with `docker compose exec app codex login --device-auth`. Complete the device flow in your browser. Never put credentials in Git or a container image. [Official Codex authentication guidance](https://learn.chatgpt.com/docs/auth) describes device login for headless machines. The server connection uses that signed-in subscription. The code-owned `telegram_access=linked_users` scope permits authenticated linked staff to share its allowance; set `owner` for owner-only operation. Credentials remain on the host, and each user's document/job ownership still applies.
5. Sign in, change the new bootstrap password, and link the same Telegram account. Verify `/health`, the AI status, a fictional queued analysis, reviewed evidence, PDF/Word downloads and a worker restart before changing the bot URL.
6. Once verified, intentionally switch the pinned bot using `docker compose exec app python -m surveyor.cli telegram-configure --replace-webhook`. This changes where the existing bot opens the Mini App; it is not run automatically.

AI configuration is versioned in code. The image pins Codex 0.160.0; validate transport compatibility and fictional cases before changing that version. Both web and AI worker use the same data/auth volumes and image. Database migrations run before the web server starts. The AI worker claims one job at a time with leases, bounded retries and compare-and-swap result publication. A crash after cloud submission can cause another model request; exactly-once cloud billing is not guaranteed.

## Backups and recovery

Use `sh deploy/backup-postgres.sh /absolute/private/backup-directory`. This exports PostgreSQL and uploaded evidence as a matching maintenance-window backup. Protect and copy backups off the server; the script does not provision external storage. Codex sign-in is deliberately excluded: authenticate again after restoration. Test a restore into a separate environment before production use.

To restore, create fresh volumes in a separate Compose project, restore the SQL dump with `pg_restore` and unpack `uploads.tar.gz` into that project's upload volume, retaining UID 10001. Run migrations, sign into Codex again, then verify document hashes, saved reports and queue state. Interrupted jobs recover after their lease expires (three attempts maximum). Do not restore over the running database.

The existing Mac database and documents are not copied automatically. A later migration needs a verified backup and an explicit cutover. The container build, Compose configuration and container migrations pass GitHub CI. TLS/domain issuance, server sign-in and phone acceptance still need verification on the selected host.
