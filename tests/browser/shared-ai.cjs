const { expect } = require("@playwright/test");

module.exports = async (page) => {
  // Real employee account and first-password-change flow in the disposable test DB.
  // Telegram/provider responses are simulated; Python tests verify the real boundary.
  const previousSurvey = await page.evaluate(() => state.survey?.id);
  await Promise.all([
    page.waitForEvent("load"),
    page.locator("#logout").click(),
  ]);
  await page.locator("#login-form [name=login]").fill("admin");
  await page
    .locator("#login-form [name=password]")
    .fill("browser-personal-password");
  await page.locator("#login-form button[type=submit]").click();
  await expect(page.locator("[data-nav=admin]")).toBeVisible();
  await page.evaluate(async () => {
    await post("/admin/employees", {
      login: "shared-ai-employee",
      password: "fictional-shared-initial",
      phone: "+998900008765",
      name: "Fictional AI employee",
      role: "employee",
      telegram_id: "222333444",
    });
  });
  await page.route("**/api/ai-pilot", (route) =>
    route.fulfill({
      json: {
        ready: true,
        documents_enabled: true,
        provider: "codex",
        telegram_access: "linked_users",
        config_revision: "test-config",
        samples: [],
      },
    }),
  );
  await Promise.all([
    page.waitForEvent("load"),
    page.locator("#logout").click(),
  ]);
  await page.locator("#login-form [name=login]").fill("shared-ai-employee");
  await page
    .locator("#login-form [name=password]")
    .fill("fictional-shared-initial");
  await page.locator("#login-form button[type=submit]").click();
  await page
    .locator("#password-form [name=old_password]")
    .fill("fictional-shared-initial");
  await page
    .locator("#password-form [name=new_password]")
    .fill("fictional-shared-changed");
  await page.locator("#password-form button[type=submit]").click();
  await expect(page.locator("[data-nav=codex]")).toBeVisible();
  await expect(page.locator("[data-nav=admin]")).toHaveCount(0);
  if (previousSurvey)
    expect(
      (await page.request.get(`/api/surveys/${previousSurvey}`)).status(),
    ).toBe(404);
  await page.unroute("**/api/ai-pilot");
  await require("./inspection-ai.cjs")(page);
  await require("./assistant.cjs")(page);
  await expect(page.locator("#assistant-analyze")).toContainText(
    "shared subscription allowance",
  );
  await page.route("**/api/ai-pilot", (route) =>
    route.fulfill({
      json: {
        ready: true,
        documents_enabled: true,
        provider: "codex",
        config_revision: "test-config",
        samples: [],
      },
    }),
  );
  await page.route("**/api/ai-pilot/surveys/*/jobs", (route) =>
    route.fulfill({ json: [] }),
  );
  await page.locator("#locale").selectOption("uz");
  await expect(page.locator("#assistant-analyze")).toContainText(
    "Obunaning umumiy limiti",
  );
  await page.screenshot({
    path: "artifacts/shared-ai-employee.png",
    fullPage: true,
  });
};
