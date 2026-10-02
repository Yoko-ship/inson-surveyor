const { defineConfig } = require("@playwright/test");
module.exports = defineConfig({
  testDir: "tests/browser",
  workers: 1,
  timeout: 60000,
  use: {
    baseURL: "http://localhost:8011",
    headless: true,
    screenshot: "only-on-failure",
  },
  outputDir: "artifacts/browser",
  webServer: {
    command:
      "uv run python scripts/prepare_browser_test.py && uv run alembic upgrade head && uv run uvicorn surveyor.main:app --host 127.0.0.1 --port 8011",
    url: "http://localhost:8011/health",
    reuseExistingServer: false,
    env: {
      DATABASE_URL: "sqlite:///./data/browser-test.db",
      STORAGE_DIR: "./data/browser-test-uploads",
      BOOTSTRAP_ADMIN_PASSWORD: "browser-initial-password",
      TELEGRAM_BOT_TOKEN: "",
      PUBLIC_URL: "http://localhost:8011",
      APP_ENV: "development",
      COOKIE_SECURE: "false",
      DATA_MODE: "synthetic",
      CODEX_TELEGRAM_ENABLED: "false",
    },
  },
});
