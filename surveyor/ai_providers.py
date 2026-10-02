"""Replaceable transports; prompts, validation and presentation belong to the app."""

import base64
import json
import re
from urllib.parse import urlsplit

import httpx
from pydantic import BaseModel, ConfigDict, Field

from surveyor import ai_config, codex_pilot
from surveyor.config import settings


class Analysis(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    fields: codex_pilot.Extraction
    summary: str = Field(max_length=3000)


SECRET = re.compile(
    r"\bsk-(?:proj-)?[A-Za-z0-9_-]{25,}|\b[0-9]{8,12}:[A-Za-z0-9_-]{35}\b|"
    r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----|\bgh[pousr]_[A-Za-z0-9]{30,}"
)


def reject_secrets(text):
    if SECRET.search(text):
        raise codex_pilot.PilotError("Обнаружены данные, похожие на секретный ключ. Удалите их и повторите.")


class CodexProvider:
    label = "Codex · ChatGPT"

    def status(self, config):
        return codex_pilot.connection()

    def generate(self, config, instructions, content, images, directory, schema):
        executable = codex_pilot.cli_path()
        status = self.status(config)
        if not executable or not status["ready"]:
            raise codex_pilot.PilotError(status["message"])
        (directory / "schema.json").write_text(json.dumps(schema.model_json_schema()), encoding="utf-8")
        args = codex_pilot.command(executable, directory, "document")
        # Trusted app instructions are a developer message; source data goes only to stdin.
        extra = [
            "--config",
            "developer_instructions=" + json.dumps(instructions, ensure_ascii=False),
            "--config",
            "model_reasoning_effort=" + json.dumps(config.codex.reasoning_effort),
        ]
        if config.codex.model:
            extra += ["--model", config.codex.model]
        for path in images:
            extra += ["--image", str(path)]
        args[-1:-1] = extra
        output = codex_pilot.run_process(
            args, cwd=directory, prompt=content, timeout=config.limits.timeout_seconds
        )
        return codex_pilot.parse_result(output, schema=schema)


def ollama_url():
    url = urlsplit(settings.ollama_base_url)
    if (
        url.scheme != "http"
        or url.hostname not in {"127.0.0.1", "localhost", "::1"}
        or url.username
        or url.password
        or url.query
        or url.fragment
        or url.path not in {"", "/"}
    ):
        raise codex_pilot.PilotError("Ollama должен использовать локальный HTTP-адрес на этом компьютере.")
    host = "[::1]" if url.hostname == "::1" else "127.0.0.1"
    return f"http://{host}:{url.port or 11434}"


def ollama_request(path, payload, timeout, max_bytes=200000):
    try:
        with httpx.Client(timeout=timeout, trust_env=False, follow_redirects=False) as client:
            with client.stream("POST", ollama_url() + path, json=payload) as response:
                response.raise_for_status()
                data = bytearray()
                for chunk in response.iter_bytes():
                    data.extend(chunk)
                    if len(data) > max_bytes:
                        raise ValueError()
                return json.loads(data)
    except (httpx.HTTPError, ValueError):
        raise codex_pilot.PilotError(
            "Ollama недоступен или вернул неверный ответ. Проверьте локальную модель."
        ) from None


class OllamaProvider:
    label = "Ollama · local"

    def details(self, config):
        model = config.ollama.model
        if not model or "cloud" in model.lower():
            raise codex_pilot.PilotError("Выберите установленную локальную модель Ollama, без cloud.")
        details = ollama_request("/api/show", {"model": model}, 5)
        if not isinstance(details, dict) or details.get("remote_host") or details.get("remote_model"):
            raise codex_pilot.PilotError("Нужна локальная модель Ollama.")
        return details

    def status(self, config):
        try:
            self.details(config)
            return {"ready": True, "message": "Локальная модель Ollama доступна."}
        except codex_pilot.PilotError as exc:
            return {"ready": False, "message": str(exc)}

    def generate(self, config, instructions, content, images, directory, schema):
        details = self.details(config)
        if images and "vision" not in details.get("capabilities", []):
            raise codex_pilot.PilotError(
                "Выбранная модель Ollama не поддерживает изображения и PDF-страницы."
            )
        message = {"role": "user", "content": content}
        if images:
            message["images"] = [base64.b64encode(p.read_bytes()).decode("ascii") for p in images]
        result = ollama_request(
            "/api/chat",
            {
                "model": config.ollama.model,
                "stream": False,
                "messages": [{"role": "system", "content": instructions}, message],
                "format": schema.model_json_schema(),
                "options": {"temperature": config.ollama.temperature, "num_predict": 6000},
            },
            config.limits.timeout_seconds,
        )
        try:
            if result.get("done") is not True or result.get("done_reason") == "length":
                raise ValueError()
            message = result["message"]
            if message.get("tool_calls"):
                raise ValueError()
            return schema.model_validate_json(message["content"]).model_dump()
        except (ValueError, KeyError, TypeError, AttributeError):
            raise codex_pilot.PilotError("ИИ вернул неполный ответ. Результат не принят.") from None


PROVIDERS = {"codex": CodexProvider(), "ollama": OllamaProvider()}


def connection(config=None):
    config = config or ai_config.load()
    if not config.enabled:
        return {"ready": False, "message": "ИИ приостановлен в настройках."}
    return PROVIDERS[config.provider].status(config)


def generate(config, text, images, directory, *, locale="ru", sample=False):
    if not config.enabled:
        raise codex_pilot.PilotError("ИИ приостановлен в настройках.")
    reject_secrets(text)
    if len(text) > config.limits.max_text_chars:
        raise ValueError("Документ превышает настроенный лимит текста.")
    instructions = ai_config.trusted_instructions(config, locale)
    reject_secrets(instructions)
    if sample:
        instructions += "\nThis is a FICTIONAL sample. Return the extraction fields only, without summary."
    else:
        instructions += "\nReturn an object containing fields and a short summary."
    content = json.dumps({"document_text": text, "attached_pages": len(images)}, ensure_ascii=False)
    schema = codex_pilot.Extraction if sample else Analysis
    result = PROVIDERS[config.provider].generate(config, instructions, content, images, directory, schema)
    # Provider implementations cannot bypass the common output contract.
    try:
        result = schema.model_validate(result).model_dump()
    except ValueError:
        raise codex_pilot.PilotError("ИИ вернул неверный формат. Результат не принят.") from None
    encoded = json.dumps(result, ensure_ascii=False)
    if len(encoded) > config.limits.max_output_chars:
        raise codex_pilot.PilotError("Ответ ИИ превышает настроенный лимит.")
    reject_secrets(encoded)
    return result
