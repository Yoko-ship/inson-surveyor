"""Export, check or import the GitHub public-statistics SQLite snapshot."""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def main():
    from surveyor.public_database import SNAPSHOT, export_snapshot, import_snapshot, verify_snapshot

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["export", "check", "import"])
    parser.add_argument("--path", type=Path, default=SNAPSHOT)
    args = parser.parse_args()
    if args.action == "check":
        result = verify_snapshot(args.path)
    else:
        from surveyor.db import SessionLocal

        if args.action == "import":
            from alembic import command
            from alembic.config import Config

            from surveyor.bootstrap import bootstrap

            command.upgrade(Config(str(Path(__file__).resolve().parents[1] / "alembic.ini")), "head")
            bootstrap()
        with SessionLocal() as db:
            result = (
                export_snapshot(db, args.path) if args.action == "export" else import_snapshot(db, args.path)
            )
            if args.action == "import":
                db.commit()
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
