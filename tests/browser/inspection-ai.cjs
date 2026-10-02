const { expect } = require("@playwright/test");

// Provider/Telegram boundary is simulated here; Python tests exercise persistence,
// signed ownership, stale versions, provenance, and exports through the real routes.
module.exports = async (page) => {
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
  await page.reload();
  await page.locator("#locale").selectOption("en");
  await page.locator("#new-survey").click();
  await page
    .locator("#create-survey [name=title]")
    .fill("AI document workflow");
  await page.locator("#create-survey button[type=submit]").click();
  await page.locator("#upload-form input").setInputFiles({
    name: "ai-contract.txt",
    mimeType: "text/plain",
    buffer: Buffer.from("Contract evidence"),
  });
  await page.locator("#upload-form button").click();
  const aiButton = page.locator("[data-ai-document]");
  await expect(aiButton).toBeVisible();
  const documentId = await aiButton.getAttribute("data-ai-document");
  let proposal = null;
  let reviewed = false;
  let evidence = null;
  await page.route(
    `**/api/ai-pilot/documents/${documentId}/proposal`,
    (route) => route.fulfill({ json: proposal }),
  );
  await page.route("**/api/ai-pilot/surveys/*/jobs", (route) => {
    if (route.request().method() === "GET") return route.fulfill({ json: [] });
    const body = route.request().postDataJSON();
    expect(body.cloud_consent).toBe(true);
    expect(body.config_revision).toBe("test-config");
    proposal = {
      id: "test-proposal",
      revision: body.revision,
      stale: false,
      display_mode: "formatted",
      summary: "**Check the original**",
      fields: [
        {
          field: "insured_sum",
          value: "1000",
          quote: "<img src=x onerror=alert(1)>",
          quote_found_in_text: true,
        },
        {
          field: "object_value",
          value: "2000",
          quote: "Value: 2000",
          quote_found_in_text: false,
        },
      ],
    };
    return route.fulfill({
      json: {
        id: "test-job",
        status: "completed",
        attempts: 1,
        kind: "document",
        document_ids: [documentId],
        result: proposal,
      },
    });
  });
  await page.route(
    `**/api/ai-pilot/documents/${documentId}/proposals/*/review`,
    async (route) => {
      const body = route.request().postDataJSON();
      expect(body.review_confirmed).toBe(true);
      expect(body.fields).toEqual({
        insured_sum: "1000",
        object_value: "2100",
      });
      const { review_confirmed, ...manualBody } = body;
      const response = await page.request.put(
        `/api/documents/${documentId}/review`,
        {
          headers: {
            "X-CSRF-Token": route.request().headers()["x-csrf-token"],
          },
          data: manualBody,
        },
      );
      expect(response.ok()).toBeTruthy();
      evidence = {
        fields: proposal.fields.map((row) => ({
          ...row,
          decision: "accepted",
        })),
      };
      reviewed = true;
      proposal = null;
      await route.fulfill({ json: await response.json() });
    },
  );
  await page.route(/\/api\/surveys\/[^/]+$/, async (route) => {
    if (route.request().method() !== "GET" || !reviewed)
      return route.continue();
    const response = await route.fetch();
    const data = await response.json();
    const doc = data.documents.find((d) => d.id === documentId);
    if (doc) doc.extracted.ai_reviews = [evidence];
    await route.fulfill({ response, json: data });
  });
  await aiButton.click();
  await page.locator("#inspection-ai-analyze [name=consent]").check();
  await page.locator("#inspection-ai-analyze button").click();
  await expect(page.locator("#inspection-ai-review")).toBeVisible();
  await expect(page.locator(".ai-summary strong")).toHaveText(
    "Check the original",
  );
  await expect(page.locator("#inspection-ai-result img")).toHaveCount(0);
  await expect(
    page.locator("#inspection-ai-review [name=use_0]"),
  ).not.toBeChecked();
  // Close/reopen resumes the persisted proposal without another model request.
  await page.locator("#modal-close").click();
  await aiButton.click();
  await expect(page.locator("#inspection-ai-review")).toBeVisible();
  await page.locator("#inspection-ai-review [name=use_0]").check();
  await page.locator("#inspection-ai-review [name=use_1]").check();
  await page.locator("#inspection-ai-review [name=value_1]").fill("2100");
  await page
    .locator("#inspection-ai-review [name=reason]")
    .fill("Compared with original document");
  await page.locator("#inspection-ai-review [name=review_confirmed]").check();
  await page.setViewportSize({ width: 390, height: 844 });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBeTruthy();
  await page.screenshot({
    path: "artifacts/inspection-ai-mobile.png",
    fullPage: true,
  });
  await page.locator("#inspection-ai-review button[type=submit]").click();
  await expect(page.locator("#review-form")).toBeVisible();
  await page.locator("[name=insured_sum]").fill("999");
  await page.locator("[data-transfer-document]").click();
  await expect(page.locator("[name=insured_sum]")).toHaveValue("1000");
  await expect(page.locator("[name=object_value]")).toHaveValue("2100");
  await expect(
    page.locator("[name=manual_review_confirmed]"),
  ).not.toBeChecked();
  await page.locator("[name=product_code]").selectOption("DEMO-FIX");
  await page.locator("[name=manual_review_confirmed]").check();
  await page.locator("#review-form button[type=submit]").click();
  await expect(page.locator("#report-view")).toContainText("2100");
  await page.unroute("**/api/ai-pilot");
  await page.unroute(`**/api/ai-pilot/documents/${documentId}/proposal`);
  await page.unroute("**/api/ai-pilot/surveys/*/jobs");
  await page.unroute(
    `**/api/ai-pilot/documents/${documentId}/proposals/*/review`,
  );
  await page.unroute(/\/api\/surveys\/[^/]+$/);
};
