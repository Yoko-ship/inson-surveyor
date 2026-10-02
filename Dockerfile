FROM node:22-bookworm-slim AS codex
ARG CODEX_VERSION=0.160.0
RUN npm install --global @openai/codex@${CODEX_VERSION}

FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy
RUN apt-get update && apt-get install -y --no-install-recommends fonts-dejavu-core && rm -rf /var/lib/apt/lists/*
COPY --from=codex /usr/local/bin/node /usr/local/bin/node
COPY --from=codex /usr/local/lib/node_modules /usr/local/lib/node_modules
RUN ln -s /usr/local/lib/node_modules/@openai/codex/bin/codex.js /usr/local/bin/codex
COPY --from=ghcr.io/astral-sh/uv:0.12.18 /uv /uvx /bin/
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev
COPY . .
RUN useradd --uid 10001 --create-home surveyor && mkdir -p /app/data/uploads /home/surveyor/.codex && chown -R surveyor:surveyor /app/data /home/surveyor/.codex
USER surveyor
ENV PATH="/app/.venv/bin:$PATH"
EXPOSE 8000
CMD ["sh", "-c", "alembic upgrade head && uvicorn surveyor.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
