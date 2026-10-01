"""Scan tracked files; report filenames only, never secret values."""

import re
import subprocess
from pathlib import Path

patterns = [rb"\b[0-9]{8,12}:[A-Za-z0-9_-]{35}\b", rb"\bsk-(?:proj-)?[A-Za-z0-9_-]{30,}\b"]
paths = subprocess.check_output(["git", "ls-files", "-z"]).split(b"\0")
bad = []
for raw in paths:
    if not raw:
        continue
    p = Path(raw.decode())
    if p.name.startswith(".env") and p.name != ".env.example":
        bad.append(str(p))
    if p.is_file() and any(re.search(pattern, p.read_bytes()) for pattern in patterns):
        bad.append(str(p))
if bad:
    raise SystemExit("Potential credentials in: " + ", ".join(set(bad)))
print("Tracked-file secret scan passed")
