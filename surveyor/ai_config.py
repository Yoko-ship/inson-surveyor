"""Code-owned AI configuration, validated from the version-controlled source."""

import hashlib
import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

DEFAULT_PATH = Path(__file__).parent / "ai" / "defaults.json"
BASELINE_PATH = Path(__file__).parent / "ai" / "guardrails.txt"


class StrictConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class Prompts(StrictConfig):
    system: str = Field(min_length=20, max_length=6000)
    defensive: str = Field(min_length=20, max_length=4000)
    extraction: str = Field(min_length=20, max_length=4000)
    style: str = Field(min_length=10, max_length=2000)
    inspection: str = Field(min_length=20, max_length=6000)
    photo: str = Field(min_length=20, max_length=6000)


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


def digest(config):
    canonical = json.dumps(config.model_dump(), sort_keys=True, ensure_ascii=False).encode()
    return hashlib.sha256(canonical).hexdigest()


def load():
    try:
        if DEFAULT_PATH.stat().st_size > 100000:
            raise ValueError()
        return AIConfig.model_validate_json(DEFAULT_PATH.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        # Fail closed; legacy runtime files must never override code-owned settings.
        raise ValueError("Конфигурация ИИ недоступна. Обратитесь к разработчику.") from None


def defaults():
    return load()


def trusted_instructions(config, locale="ru", task="extraction"):
    # Only version-controlled developer configuration belongs here. Never interpolate documents.
    prompts = config.prompts
    return "\n\n".join(
        [
            BASELINE_PATH.read_text(encoding="utf-8"),
            prompts.system,
            prompts.defensive,
            getattr(prompts, task),
            prompts.style,
            f"Write the summary in {locale}. Preserve source quotations verbatim.",
        ]
    )
