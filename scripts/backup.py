"""Create/verify backups and restore to a NEW directory; never overwrites the live app."""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from surveyor.maintenance import create_backup, restore_backup, verify_backup  # noqa: E402

parser = argparse.ArgumentParser()
parser.add_argument("action", choices=["create", "verify", "restore"])
parser.add_argument("--backup")
parser.add_argument("--destination")
args = parser.parse_args()
if args.action == "create":
    print(create_backup())
elif args.action == "verify":
    if not args.backup:
        parser.error("--backup is required")
    data = verify_backup(args.backup)
    print(f"Verified {len(data['files'])} files and database integrity")
else:
    if not args.backup or not args.destination:
        parser.error("--backup and --destination are required")
    print(restore_backup(args.backup, args.destination))
