"""Create ignored local settings without printing credentials."""

import secrets
from pathlib import Path

root = Path(__file__).resolve().parents[1]
target = root / ".env"
if target.exists():
    print(".env already exists; preserved")
else:
    text = (root / ".env.example").read_text()
    text = text.replace("BOOTSTRAP_ADMIN_PASSWORD=", "BOOTSTRAP_ADMIN_PASSWORD=" + secrets.token_urlsafe(24))
    text = text.replace("TELEGRAM_WEBHOOK_SECRET=", "TELEGRAM_WEBHOOK_SECRET=" + secrets.token_urlsafe(32))
    target.write_text(text)
    target.chmod(0o600)
    print("Created .env (permissions 0600). Initial admin password is stored there.")
