# Operations

## Local setup and credentials

Run `sh scripts/run_local.sh`. `.env` is intentionally untracked. Bootstrap credentials create the first admin only on an empty users table. Login and change that password, then create employees/underwriters/actuaries in Administration. All local data is synthetic by default.

Never commit `.env`, databases, uploaded client files or generated reports. Before any release run `uv run python scripts/check_secrets.py` after staging the intended files. The script reports filenames rather than secret values.

## GitHub configuration

CI checks Python lint/format, JavaScript syntax, calculation/workflow tests, migrations against SQLite and PostgreSQL, dependency vulnerabilities and tracked secrets. CODEOWNERS assigns the repository owner; Dependabot monitors Python, GitHub Actions and Docker dependencies. No deployment secrets are needed for local work.

Recommended repository settings: private visibility; squash merge; delete merged branches; disable wiki; Actions default token read-only; require CI on pull requests; prevent force pushes/deletion of main. Enforcement availability depends on the GitHub account plan for private repositories. The branch rules must not be described as enforced if the GitHub API refuses them.

Configured repository: [Yoko-ship/inson-surveyor](https://github.com/Yoko-ship/inson-surveyor), private, default branch `main`, squash-only merges, automatic merged-branch deletion, wiki disabled, read-only Actions token and vulnerability alerts enabled. The request to protect `main` returned HTTP 403: GitHub requires Pro (or a public repository). Protection is therefore **not enforced**; private visibility was preserved.

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

This token already has an external webhook. Local startup never alters it. Once an HTTPS deployment is intentionally chosen, run the documented configure command. Compare `/health`, login, fresh Mini App signed authorization, report download and explicit send-to-self from a real phone. A working desktop browser does not establish mobile Telegram acceptance.

## Production gates

HTTPS cookies; Uzbekistan hosting for real data as required by the supplied ТЗ; actual approved tariffs; reviewed statutory formulas; calibrated risk settings; non-demo accounts; persistent database/uploads; tested backups; protected logs; live source permission review; complete translations; real Telegram phone test. `HOSTING_COUNTRY` is an assertion, not an independent residency detector.
