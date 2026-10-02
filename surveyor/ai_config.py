"""Provider-independent AI configuration: validated snapshots and atomic revisions."""

import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from surveyor.config import settings
from surveyor.file_lock import locked_file

DEFAULT_PATH = Path(__file__).parent / "ai" / "defaults.json"
BASELINE_PATH = Path(__file__).parent / "ai" / "guardrails.txt"


class StrictConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class Prompts(StrictConfig):
    system: str = Field(min_length=20, max_length=6000)
    defensive: str = Field(min_length=20, max_length=4000)
    extraction: str = Field(min_length=20, max_length=4000)
    style: str = Field(min_length=10, max_length=2000)


class Limits(StrictConfig):
    max_pages: int = Field(default=10, ge=1, le=10)
    max_text_chars: int = Field(default=60000, ge=1000, le=60000)
    timeout_seconds: int = Field(default=90, ge=10, le=90)
    max_output_chars: int = Field(default=20000, ge=2000, le=50000)


class CodexOptions(StrictConfig):
    model: str = Field(default="", max_length=100, pattern=r"^[A-Za-z0-9._:-]*$")
    reasoning_effort: Literal["low", "medium", "high"] = "medium"


class OllamaOptions(StrictConfig):
    model: str = Field(default="", max_length=150, pattern=r"^[A-Za-z0-9._:/-]*$")
    temperature: float = Field(default=0.0, ge=0, le=1)


class AIConfig(StrictConfig):
    schema_version: Literal[1] = 1
    enabled: bool = True
    provider: Literal["codex", "ollama"] = "codex"
    codex: CodexOptions = Field(default_factory=CodexOptions)
    ollama: OllamaOptions = Field(default_factory=OllamaOptions)
    prompts: Prompts
    limits: Limits = Field(default_factory=Limits)
    display_mode: Literal["formatted", "plain"] = "formatted"

    @model_validator(mode="after")
    def selected_model(self):
        if self.provider == "ollama" and not self.ollama.model.strip():
            raise ValueError("Укажите установленную модель Ollama.")
        return self


class ConfigConflict(ValueError):
    pass


def directory():
    return settings.ai_config_dir


def digest(config):
    canonical = json.dumps(config.model_dump(), sort_keys=True, ensure_ascii=False).encode()
    return hashlib.sha256(canonical).hexdigest()


def defaults():
    return AIConfig.model_validate_json(DEFAULT_PATH.read_text(encoding="utf-8"))


def load():
    path = directory() / "active.json"
    if not path.exists():
        return defaults()
    try:
        if path.stat().st_size > 100000:
            raise ValueError()
        return AIConfig.model_validate_json(path.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        # Do not silently run with different prompts after a corrupt edit.
        raise ValueError("Настройки ИИ повреждены. Восстановите проверенную версию конфигурации.") from None


def atomic_write(path, content):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    descriptor, temporary = tempfile.mkstemp(dir=path.parent, prefix=".ai-")
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def save(config, expected_revision):
    # Validate even callers outside HTTP; configuration is data, never executable code.
    config = AIConfig.model_validate(config.model_dump())
    from surveyor.ai_providers import reject_secrets

    reject_secrets(config.model_dump_json())
    with locked_file(directory() / "settings.lock"):
        current = load()
        if digest(current) != expected_revision:
            raise ConfigConflict("Настройки уже изменены. Обновите страницу перед сохранением.")
        for snapshot in (current, config):
            path = directory() / "history" / f"{digest(snapshot)}.json"
            if not path.exists():
                atomic_write(path, snapshot.model_dump_json(indent=2) + "\n")
        atomic_write(directory() / "active.json", config.model_dump_json(indent=2) + "\n")
    return digest(config)


def trusted_instructions(config, locale="ru"):
    # Only administrator configuration belongs here. Never interpolate documents.
    prompts = config.prompts
    return "\n\n".join(
        [
            BASELINE_PATH.read_text(encoding="utf-8"),
            prompts.system,
            prompts.defensive,
            prompts.extraction,
            prompts.style,
            f"Write the summary in {locale}. Preserve source quotations verbatim.",
        ]
    )
