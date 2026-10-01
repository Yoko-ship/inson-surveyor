"""Create ignored local settings without printing credentials."""

import os
import secrets
from pathlib import Path

root = Path(__file__).resolve().parents[1]
target = root / ".env"
if target.exists():
    print(".env already exists; preserved")
else:
    text = (root / ".env.example").read_text(encoding="utf-8")
    text = text.replace("BOOTSTRAP_ADMIN_PASSWORD=", "BOOTSTRAP_ADMIN_PASSWORD=" + secrets.token_urlsafe(24))
    text = text.replace("TELEGRAM_WEBHOOK_SECRET=", "TELEGRAM_WEBHOOK_SECRET=" + secrets.token_urlsafe(32))
    target.write_text(text, encoding="utf-8")
    target.chmod(0o600)
    permissions = "Windows user-folder permissions" if os.name == "nt" else "permissions 0600"
    print(f"Created .env ({permissions}). Initial admin password is stored there.")
