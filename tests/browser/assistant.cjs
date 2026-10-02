const { expect } = require("@playwright/test");

module.exports = async (page) => {
  await page.route("**/api/ai-pilot", (route) =>
    route.fulfill({
      json: {
        ready: true,
        documents_enabled: true,
        provider: "codex",
        config_revision: "a".repeat(64),
        samples: [],
      },
    }),
  );
  let job = null;
  let polls = 0;
  await page.route("**/api/ai-pilot/surveys/*/jobs", (route) => {
    if (route.request().method() === "GET")
      return route.fulfill({ json: job ? [job] : [] });
    const body = route.request().postDataJSON();
    expect(body.kind).toBe("inspection");
    expect(body.cloud_consent).toBe(true);
    expect(body.document_ids.length).toBe(1);
    job = {
      id: "assistant-job",
      status: "queued",
      kind: "inspection",
      attempts: 0,
      document_ids: body.document_ids,
      result: {},
    };
    return route.fulfill({ json: job });
  });
  await page.route("**/api/ai-pilot/jobs/assistant-job", (route) => {
    polls += 1;
    job.status = polls > 1 ? "completed" : "running";
    job.attempts = 1;
    if (job.status === "completed")
      job.result = {
        findings: [
          {
            id: "findings_0",
            category: "evidence",
            text: "**Review source evidence**",
            citations: [
              {
                source_id: job.document_ids[0],
                filename: "ai-contract.txt",
                quote: "<script>alert(1)</script>",
                quote_found_in_text: true,
              },
            ],
          },
        ],
        explanation: [],
        questions: ["Confirm object ownership?"],
        display_mode: "formatted",
      };
    return route.fulfill({ json: job });
  });
  await page.route("**/api/ai-pilot/jobs/assistant-job/review", (route) => {
    const body = route.request().postDataJSON();
    expect(body.accepted).toEqual({
      findings_0: "Human-verified source evidence",
    });
    expect(body.review_confirmed).toBe(true);
    job.status = "reviewed";
    return route.fulfill({ json: { revision: body.revision + 1 } });
  });
  await page.locator("[data-step=review]").click();
  await page.locator("[name=object_type]").selectOption("housing");
  await page.locator("#save-draft").click();
  await expect(page.locator("#guidance-form")).toBeVisible();
  await page
    .locator("#guidance-form textarea")
    .first()
    .fill("Fictional ownership document checked");
  await page.locator("#guidance-form button[type=submit]").click();
  await expect(page.locator("#guidance-form textarea").first()).toHaveValue(
    "Fictional ownership document checked",
  );
  await page.locator("#assistant-analyze [name=document]").check();
  await page.locator("#assistant-analyze [name=consent]").check();
  await page.locator("#assistant-analyze button[type=submit]").click();
  await expect(page.locator("#assistant-result [role=status]")).toBeVisible();
  // Simulate leaving the screen and resuming the server-side job.
  await page.locator("[data-step=files]").click();
  await page.locator("[data-step=assistant]").click();
  await expect(page.locator("#assistant-review")).toBeVisible({
    timeout: 10000,
  });
  await expect(page.locator("[data-ai-text] strong")).toHaveText(
    "Review source evidence",
  );
  await expect(page.locator("#assistant-result script")).toHaveCount(0);
  await page.locator("#assistant-review [name=use_0]").check();
  await page
    .locator("#assistant-review [name=text_0]")
    .fill("Human-verified source evidence");
  await page
    .locator("#assistant-review [name=reason]")
    .fill("Checked against the fictional original");
  await page.locator("#assistant-review [name=confirmed]").check();
  await page.setViewportSize({ width: 390, height: 844 });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBeTruthy();
  await page.screenshot({
    path: "artifacts/assistant-mobile.png",
    fullPage: true,
  });
  await page.locator("#assistant-review button[type=submit]").click();
  await expect(page.locator("#guidance-form")).toBeVisible();
  await page.unroute("**/api/ai-pilot");
  await page.unroute("**/api/ai-pilot/surveys/*/jobs");
  await page.unroute("**/api/ai-pilot/jobs/assistant-job");
  await page.unroute("**/api/ai-pilot/jobs/assistant-job/review");
};
