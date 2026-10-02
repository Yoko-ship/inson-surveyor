"""Inspect, validate and apply AI configuration without running an AI provider."""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from surveyor import ai_config  # noqa: E402
from surveyor.ai_providers import reject_secrets  # noqa: E402
from surveyor.codex_pilot import PilotError  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["show", "validate", "apply", "history"])
    parser.add_argument("file", nargs="?", type=Path)
    parser.add_argument("--expected-revision", help="Required for apply; read it with show first")
    args = parser.parse_args()
    if args.command == "show":
        config = ai_config.load()
        reject_secrets(config.model_dump_json())
        print(
            json.dumps(
                {"revision": ai_config.digest(config), "config": config.model_dump()},
                ensure_ascii=False,
                indent=2,
            )
        )
    elif args.command == "history":
        for path in sorted((ai_config.directory() / "history").glob("*.json")):
            print(path)
    else:
        if not args.file or args.file.stat().st_size > 100000:
            parser.error("Provide a config JSON file up to 100 KB")
        config = ai_config.AIConfig.model_validate_json(args.file.read_text(encoding="utf-8"))
        reject_secrets(config.model_dump_json())
        if args.command == "validate":
            print("Valid AI configuration: " + ai_config.digest(config))
        else:
            if not args.expected_revision:
                parser.error("apply requires --expected-revision")
            print("Applied revision: " + ai_config.save(config, args.expected_revision))


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, PilotError):
        raise SystemExit(
            "Configuration rejected. Check its schema, limits, file and expected revision."
        ) from None
