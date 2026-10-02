"""Inspect and validate code-owned AI configuration without running a provider."""

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
    parser.add_argument("command", choices=["show", "validate"])
    parser.add_argument("file", nargs="?", type=Path)
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
    else:
        path = args.file or ai_config.DEFAULT_PATH
        if path.stat().st_size > 100000:
            parser.error("Provide a config JSON file up to 100 KB")
        config = ai_config.AIConfig.model_validate_json(path.read_text(encoding="utf-8"))
        reject_secrets(config.model_dump_json())
        print("Valid AI configuration: " + ai_config.digest(config))


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, PilotError):
        raise SystemExit(
            "Configuration rejected. Check the version-controlled file, schema and limits."
        ) from None
