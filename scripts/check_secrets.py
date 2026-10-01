"""Scan tracked files and Git history; never expose credential matches."""

import re
import subprocess
import sys
from pathlib import Path

patterns = [
    rb"\b[0-9]{8,12}:[A-Za-z0-9_-]{35}\b",
    rb"\bsk-(?:proj-)?[A-Za-z0-9_-]{30,}\b",
    rb"\bgh[pousr]_[A-Za-z0-9]{30,}\b",
    rb"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----",
]
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
if "--history" in sys.argv:
    objects = subprocess.check_output(["git", "rev-list", "--objects", "--all"]).decode().splitlines()
    with subprocess.Popen(
        ["git", "cat-file", "--batch"], stdin=subprocess.PIPE, stdout=subprocess.PIPE
    ) as proc:
        for line in objects:
            sha, _, name = line.partition(" ")
            proc.stdin.write((sha + "\n").encode())
            proc.stdin.flush()
            header = proc.stdout.readline().decode().split()
            data = proc.stdout.read(int(header[2]))
            proc.stdout.read(1)
            env_file = Path(name).name.startswith(".env") and Path(name).name != ".env.example"
            if header[1] == "blob" and (env_file or any(re.search(p, data) for p in patterns)):
                bad.append(f"history blob {sha[:12]}")
        proc.stdin.close()
        proc.wait()
if bad:
    raise SystemExit("Potential credentials in: " + ", ".join(set(bad)))
print(
    "Secret scan passed"
    + (" (tracked files and Git history)" if "--history" in sys.argv else " (tracked files)")
)
