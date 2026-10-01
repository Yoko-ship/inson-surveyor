"""Install the supplied reference PDF after verifying it matches the catalogue."""

import argparse
import hashlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from surveyor.config import settings  # noqa: E402
from surveyor.tariff_policy import catalog  # noqa: E402


def install(source: Path):
    content = source.read_bytes()
    policy = catalog()
    if hashlib.sha256(content).hexdigest() != policy["sha256"]:
        raise ValueError("PDF does not match the reviewed catalogue; review a new version before installing")
    target = settings.storage_dir / "policies" / f"{policy['id']}.pdf"
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists() and target.read_bytes() == content:
        return target
    temporary = target.with_suffix(".pdf.tmp")
    temporary.write_bytes(content)
    temporary.replace(target)
    return target


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    args = parser.parse_args()
    print(f"Reference PDF installed: {install(args.source)}")
