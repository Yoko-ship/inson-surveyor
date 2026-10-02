const { expect } = require("@playwright/test");

module.exports = async (page) => {
  await page.route("**/api/ai-pilot", (route) =>
    route.fulfill({
      json: {
        ready: true,
        message: "Вход через ChatGPT найден.",
        samples: [
          {
            id: "text",
            title: "Учебный договор · текст",
            text: "УЧЕБНЫЙ ДОГОВОР\nТариф: 0,5%",
          },
        ],
      },
    }),
  );
  let calls = 0;
  await page.route("**/api/ai-pilot/run", (route) => {
    calls += 1;
    expect(route.request().postDataJSON()).toEqual({ sample_id: "text" });
    return route.fulfill({
      json: {
        saved: false,
        sample_id: "text",
        fields: [
          {
            field: "declared_rate",
            value: "0.5",
            expected: "0.5",
            quote: "Тариф: 0,5%",
            matches: true,
          },
          {
            field: "object_description",
            value: "<img src=x onerror=alert(1)>",
            expected: null,
            quote: "<script>alert(1)</script>",
            matches: false,
          },
        ],
      },
    });
  });
  await page.reload();
  await page.locator("[data-nav=codex]").click();
  await expect(page.locator("#codex-pilot-form")).toBeVisible();
  await page.locator("#locale").selectOption("en");
  await expect(page.locator("#content h1")).toHaveText("Codex · sample pilot");
  await page.getByRole("button", { name: "Read with Codex" }).click();
  await expect(page.locator("#codex-result")).toBeVisible();
  await expect(page.locator("#codex-result tbody tr")).toHaveCount(2);
  await expect(page.locator("#codex-result")).toContainText(
    "not been saved to an inspection",
  );
  await expect(
    page.locator("#codex-result script, #codex-result img"),
  ).toHaveCount(0);
  await page.screenshot({
    path: "artifacts/codex-pilot-desktop.png",
    fullPage: true,
  });
  await page.setViewportSize({ width: 390, height: 844 });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBeTruthy();
  await page.screenshot({
    path: "artifacts/codex-pilot-mobile.png",
    fullPage: true,
  });
  await page.setViewportSize({ width: 1280, height: 900 });
  await page.locator("#locale").selectOption("uz");
  await expect(page.locator("#content h1")).toHaveText("Codex · o‘quv sinovi");
  expect(calls).toBe(1);
  await page.unroute("**/api/ai-pilot");
  await page.unroute("**/api/ai-pilot/run");
  await page.route("**/api/ai-pilot", (route) =>
    route.fulfill({
      json: {
        ready: true,
        documents_enabled: true,
        message: "Signed in",
        samples: [{ id: "text", title: "Sample", text: "Sample" }],
      },
    }),
  );
  await page.evaluate(() => {
    window.Telegram = { WebApp: { initData: "signed-test-proof" } };
  });
  let uploads = 0;
  await page.route("**/api/ai-pilot/analyze", (route) => {
    uploads += 1;
    expect(route.request().headers()["x-telegram-init-data"]).toBe(
      "signed-test-proof",
    );
    expect(route.request().postData()).toContain('name="cloud_consent"');
    return route.fulfill({
      json: {
        saved: false,
        summary:
          "**Check the source**\n- Keep 0.5% unchanged.\n<img src=x onerror=alert(1)>",
        display_mode: "formatted",
        fields: [
          {
            field: "object_description",
            value: "<img src=x onerror=alert(1)>",
            quote: "<script>alert(1)</script>",
            status: "needs_review",
            quote_found_in_text: false,
          },
        ],
      },
    });
  });
  await page.locator("#locale").selectOption("en");
  await expect(page.locator("#content h1")).toHaveText("Codex · my documents");
  await page.locator('#codex-document-form input[type="file"]').setInputFiles({
    name: "contract.txt",
    mimeType: "text/plain",
    buffer: Buffer.from("Test contract"),
  });
  await page.locator('#codex-document-form input[type="checkbox"]').check();
  await page.locator("#codex-document-form button").click();
  await expect(page.locator("#document-result")).toBeVisible();
  await expect(page.locator("#ai-summary strong")).toHaveText(
    "Check the source",
  );
  await expect(page.locator("#ai-summary")).not.toContainText("**");
  await expect(
    page.locator("#document-result script, #document-result img"),
  ).toHaveCount(0);
  await page.setViewportSize({ width: 390, height: 844 });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBeTruthy();
  await page.screenshot({
    path: "artifacts/codex-documents-mobile.png",
    fullPage: true,
  });
  expect(uploads).toBe(1);
  await expect(page.locator("#ai-settings, #ai-settings-form")).toHaveCount(0);
  expect((await page.request.get("/api/ai-pilot/settings")).status()).toBe(404);
  expect(
    (
      await page.request.put("/api/ai-pilot/settings", {
        data: { provider: "ollama" },
      })
    ).status(),
  ).toBe(404);
  expect((await page.request.get("/static/ai_settings.js")).status()).toBe(404);
  await page.evaluate(() =>
    window.SurveyorAIText.render(
      document.querySelector("#ai-summary"),
      "**INSON**",
      "plain",
    ),
  );
  await expect(page.locator("#ai-summary")).toHaveText("INSON");
  await expect(page.locator("#ai-summary strong")).toHaveCount(0);
  await page.unroute("**/api/ai-pilot");
  await page.unroute("**/api/ai-pilot/analyze");
};
