"""Codex CLI primitives and fixed-sample checks. Credentials stay with Codex."""

import json
import os
import shutil
import signal
import subprocess
import tempfile
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, ValidationError, create_model

from surveyor.config import settings
from surveyor.pilot_samples import FIELDS, SAMPLES, scan_png


class PilotError(Exception):
    """A redacted failure safe to show in the pilot UI."""


class Reading(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    value: str | None = Field(max_length=2000)
    quote: str = Field(max_length=2000)


Extraction = create_model(
    "Extraction",
    __config__=ConfigDict(extra="forbid", strict=True),
    **{name: (Reading, ...) for name in FIELDS},
)

# This CLI version emits a startup diagnostic when the intentionally disabled
# code-mode host is unavailable. It is not a failed turn or a tool invocation.
DISABLED_CODE_MODE_NOTICE = (
    "Code Mode is unavailable because code-mode host is disabled. "
    "Code mode will fail closed; enable `features.code_mode_host` and install `codex-code-mode-host`."
)


def cli_path():
    if settings.codex_cli_path:
        path = Path(settings.codex_cli_path)
        return path.resolve() if path.is_file() else None
    found = shutil.which("codex.exe" if os.name == "nt" else "codex")
    if found:
        return Path(found)
    root = Path(os.environ.get("LOCALAPPDATA", "")) / "OpenAI" / "Codex" / "bin"
    candidates = list(root.glob("*/codex.exe")) if os.name == "nt" and root.is_dir() else []
    return max(candidates, key=lambda p: p.stat().st_mtime) if candidates else None


def child_environment():
    # No application secrets, API keys, Telegram tokens or inherited tool configuration.
    allowed = {
        "PATH",
        "PATHEXT",
        "SYSTEMROOT",
        "WINDIR",
        "COMSPEC",
        "TEMP",
        "TMP",
        "TMPDIR",
        "USERPROFILE",
        "HOME",
        "HOMEDRIVE",
        "HOMEPATH",
        "LOCALAPPDATA",
        "APPDATA",
        "CODEX_HOME",
    }
    return {k: v for k, v in os.environ.items() if k.upper() in allowed}


def run_process(args, *, cwd=None, prompt=None, timeout=10, login_status=False):
    try:
        process = subprocess.Popen(
            [str(arg) for arg in args],
            cwd=cwd,
            env=child_environment(),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            start_new_session=os.name != "nt",
        )
    except OSError:
        raise PilotError("Не удалось запустить Codex. Проверьте локальную установку.") from None
    try:
        stdout, stderr = process.communicate(prompt, timeout=timeout)
    except subprocess.TimeoutExpired:
        stop_process(process)
        process.communicate(timeout=5)
        raise PilotError("Codex не ответил вовремя. Попробуйте позже.") from None
    if process.returncode:
        raise PilotError("Codex не завершил запрос. Проверьте вход, соединение и лимиты в Codex.")
    if login_status:
        return "chatgpt" if "Logged in using ChatGPT" in stdout + stderr else "unavailable"
    return stdout


def stop_process(process):
    """Terminate the CLI and wrapper descendants, which can otherwise keep pipes open."""
    if os.name == "nt":
        subprocess.run(
            ["taskkill", "/PID", str(process.pid), "/T", "/F"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=5,
            check=False,
        )
        process.kill()
    else:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass


def connection():
    executable = cli_path()
    if not executable:
        return {"ready": False, "message": "Codex не найден на этом компьютере."}
    try:
        # This command reports the authentication mode, never the underlying tokens.
        ready = run_process([executable, "login", "status"], login_status=True) == "chatgpt"
        return {
            "ready": ready,
            "message": "Вход через ChatGPT найден."
            if ready
            else "Войдите в Codex через ChatGPT на этом компьютере.",
        }
    except PilotError as exc:
        return {"ready": False, "message": str(exc)}


def command(executable, directory, sample_id):
    args = [
        str(executable),
        "exec",
        "--ignore-user-config",
        "--ephemeral",
        "--skip-git-repo-check",
        "--sandbox",
        "read-only",
        "--cd",
        str(directory),
        "--json",
        "--output-schema",
        str(directory / "schema.json"),
    ]
    for feature in (
        "shell_tool",
        "shell_snapshot",
        "hooks",
        "apps",
        "plugins",
        "remote_plugin",
        "multi_agent",
        "computer_use",
        "browser_use",
        "code_mode",
        "code_mode_only",
        "code_mode_host",
        "memories",
    ):
        args.extend(["--disable", feature])
    for config in (
        'approval_policy="never"',
        'web_search="disabled"',
        "project_doc_max_bytes=0",
        "mcp_servers={}",
    ):
        args.extend(["--config", config])
    if sample_id == "scan":
        args.extend(["--image", str(directory / "sample.png")])
    args.append("-")  # Document text goes to stdin, never a shell command or command-line argument.
    return args


def parse_result(stdout, schema=Extraction):
    if len(stdout) > 2_000_000:
        raise PilotError("Ответ Codex слишком большой.")
    try:
        events = [json.loads(line) for line in stdout.splitlines() if line.strip()]
        if not any(e.get("type") == "turn.completed" for e in events) or any(
            e.get("type") in {"error", "turn.failed"} for e in events
        ):
            raise ValueError()
        turn_started = False
        for event in events:
            if event.get("type") == "turn.started":
                turn_started = True
            if event.get("type") in {"item.started", "item.completed"}:
                item = event.get("item", {})
                if (
                    not turn_started
                    and item.get("type") == "error"
                    and item.get("message") == DISABLED_CODE_MODE_NOTICE
                ):
                    continue
                if item.get("type") not in {"agent_message", "reasoning"}:
                    raise ValueError()
        messages = [
            e["item"]["text"]
            for e in events
            if e.get("type") == "item.completed" and e.get("item", {}).get("type") == "agent_message"
        ]
        return schema.model_validate_json(messages[-1]).model_dump()
    except (ValueError, KeyError, IndexError, TypeError, AttributeError, ValidationError):
        raise PilotError("Codex вернул неполный ответ. Поля не приняты; попробуйте снова.") from None


def assess(sample_id, readings):
    sample = SAMPLES[sample_id]
    rows = []
    for name in FIELDS:
        value, quote = readings[name]["value"], readings[name]["quote"]
        valid = value is None and not quote
        if value is not None:
            valid = bool(quote.strip()) and quote in sample["text"]
            if name in FIELDS[:5]:
                try:
                    number = Decimal(value)
                    valid &= number.is_finite() and 0 <= number <= Decimal("1e18")
                    if name == "declared_rate":
                        valid &= number <= 100
                    if name == "term_days":
                        valid &= 1 <= number <= 36500 and number == number.to_integral_value()
                except InvalidOperation:
                    valid = False
            elif name.startswith("contract_"):
                try:
                    valid &= date.fromisoformat(value).isoformat() == value
                except ValueError:
                    valid = False
        expected = sample["expected"][name]
        matches = value == expected
        if name in FIELDS[:5] and value is not None and expected is not None and valid:
            matches = Decimal(value) == Decimal(expected)
        rows.append(
            {
                "field": name,
                "value": value,
                "quote": quote,
                "expected": expected,
                "matches": bool(matches and valid),
                "evidence_valid": bool(valid),
                "status": "needs_review",
            }
        )
    return rows


def recognize(sample_id):
    if sample_id not in SAMPLES:
        raise PilotError("Неизвестный учебный пример.")
    from surveyor import ai_config, ai_providers

    config = ai_config.load()
    with tempfile.TemporaryDirectory(prefix="surveyor-codex-") as folder:
        directory = Path(folder)
        images = []
        if sample_id == "scan":
            (directory / "sample.png").write_bytes(scan_png())
            images = [directory / "sample.png"]
        readings = ai_providers.generate(
            config, "" if images else SAMPLES[sample_id]["text"], images, directory, sample=True
        )
    return {
        "sample_id": sample_id,
        "fields": assess(sample_id, readings),
        "saved": False,
        "config_revision": ai_config.digest(config),
        "provider": config.provider,
    }
