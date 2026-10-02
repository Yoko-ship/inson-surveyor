const { test, expect } = require("@playwright/test");
test("local browser: first login, documents, fixed premium, exports, admin and mobile", async ({
  page,
}) => {
  const errors = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.goto("/");
  await page.locator("#login-form [name=login]").fill("admin");
  await page
    .locator("#login-form [name=password]")
    .fill("browser-initial-password");
  await page.locator("#login-form button[type=submit]").click();
  await expect(page.locator("#password-form")).toBeVisible();
  await page.locator("[name=old_password]").fill("browser-initial-password");
  await page.locator("[name=new_password]").fill("browser-personal-password");
  await page.locator("#password-form button[type=submit]").click();
  await expect(page.locator("#new-survey")).toBeVisible();
  await page.screenshot({ path: "artifacts/dashboard.png", fullPage: true });
  await page.locator("#new-survey").click();
  await page
    .locator("[name=title]")
    .fill("Учебный объект · трёхлетний договор");
  await page.locator("#create-survey button[type=submit]").click();
  await page.locator("#upload-form input").setInputFiles({
    name: "branch-request.txt",
    mimeType: "text/plain",
    buffer: Buffer.from(
      "Запрос филиала\nСтраховая сумма: 100 000 000\nТариф: 0,5\nСтраховая премия: 503870",
    ),
  });
  await page.locator("#upload-form button").click();
  await expect(page.locator(".file-card")).toContainText("branch-request.txt");
  await page.locator("#to-review").click();
  await page.locator("[name=product_code]").selectOption("DEMO-FIX");
  await page.locator("[name=object_value]").fill("100000000");
  await page.locator("[name=term_days]").fill("1095");
  await page.locator("[name=manual_review_confirmed]").check();
  await page.locator("#review-form button[type=submit]").click();
  await expect(page.locator("#report-view .result-value")).toContainText("500");
  await expect(page.locator("#report-view")).toContainText("3 870");
  const downloadPromise = page.waitForEvent("download");
  await page.getByRole("link", { name: "↓ PDF" }).click();
  const download = await downloadPromise;
  expect(download.suggestedFilename()).toMatch(/surveyor-.*\.pdf/);
  await page.screenshot({ path: "artifacts/report.png", fullPage: true });
  await page.locator("[data-nav=admin]").click();
  await page.locator("#add-product").click();
  await page.locator("#product-form [name=code]").fill("BROWSER-P");
  await page.locator("#product-form [name=name]").fill("Browser test product");
  await page.locator("#product-form [name=rate]").fill("0.5");
  await page.locator("#product-form [name=min_rate]").fill("0.3");
  await page.locator("#product-form button[type=submit]").click();
  await expect(page.locator("#admin-content")).toContainText("BROWSER-P");
  await page.locator("[data-tab=employees]").click();
  await expect(page.locator("#admin-content")).toContainText("Администратор");
  await page.setViewportSize({ width: 390, height: 844 });
  await page.locator("[data-nav=surveys]").click();
  await expect(page.locator("#new-survey")).toBeVisible();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBeTruthy();
  await page.screenshot({ path: "artifacts/mobile.png", fullPage: true });
  await page.setViewportSize({ width: 1280, height: 900 });
  await page.locator("[data-nav=admin]").click();
  await page.locator("[data-tab=templates]").click();
  await page.locator("#new-template").click();
  await expect(
    page.locator("#template-form [name=valuation_tolerance]"),
  ).toBeVisible();
  await page.locator("#template-form [name=class_code]").fill("BROWSER-CLASS");
  await page
    .locator("#template-form [name=name]")
    .fill("Browser class template");
  await page
    .locator("#template-form [name=large_object_threshold]")
    .fill("1000000000");
  await page.locator("#add-indicator-rule").click();
  await page.locator(".indicator-rule [name=metric]").fill("registered_crimes");
  await page.locator(".indicator-rule [name=baseline]").fill("1000");
  await page.locator(".indicator-rule [data-object-type=housing]").check();
  await page.locator("#template-form button[type=submit]").click();
  await expect(page.locator("#admin-content")).toContainText("BROWSER-CLASS");
  await page.locator("[data-nav=sources]").click();
  await page.locator('[data-source-import="stat"]').click();
  await page.locator("#source-import input").setInputFiles({
    name: "source.csv",
    mimeType: "text/csv",
    buffer: Buffer.from(
      "metric,period,value,unit,source_url,observation_date\nregional_test,2025,10,count,https://stat.uz/,2025-12-31\n",
    ),
  });
  await page.locator("#source-import button").click();
  await expect(page.locator("#source-preview")).toContainText("regional_test");
  await page.locator("#source-confirm").click();
  await expect(page.locator("#indicator-list")).toContainText("regional_test");
  await page.locator("#locale").selectOption("en");
  await expect(page.locator("#content h1")).toHaveText("Public data");
  await expect(page.locator("#content")).toContainText("Source registry");
  await page.locator("[data-nav=calculator]").click();
  await expect(page.locator("#content")).toContainText(
    "Calculation parameters",
  );
  await expect(
    page.getByRole("button", { name: "Calculate premium →" }),
  ).toBeVisible();
  await page.locator("#calculator-form [name=insured_sum]").fill("2000");
  await page.locator("#calculator-form [name=object_value]").fill("2000");
  await page.locator("#calculator-form button[type=submit]").click();
  await expect(page.locator("#calculator-result")).toContainText(
    "Annual equivalent of the recommendation",
  );
  await page.locator("[data-nav=admin]").click();
  await page.locator("[data-tab=templates]").click();
  await page.locator("#new-template").click();
  await expect(page.locator("#modal")).toContainText("Valuation rules");
  await page.locator("#modal-close").click();
  await page.locator("#locale").selectOption("uz");
  await page.locator("[data-nav=calculator]").click();
  await expect(
    page.getByRole("button", { name: "Mukofotni hisoblash →" }),
  ).toBeVisible();
  await page.screenshot({
    path: "artifacts/uzbek-calculator.png",
    fullPage: true,
  });
  await page.locator("[data-nav=admin]").click();
  await page.locator("[data-tab=operations]").click();
  await expect(page.locator("#admin-content")).toContainText("Tizim holati");
  await page.locator("#locale").selectOption("en");
  await page.locator("[data-tab=indicators]").click();
  await expect(page.locator("#market-quote-form")).toBeVisible();
  await page
    .locator("#market-quote-form [name=class_code]")
    .selectOption("property");
  await page
    .locator("#market-quote-form [name=object_type]")
    .selectOption("housing");
  await page.locator("#market-quote-form [name=rate]").fill("0.6");
  await page.locator("#market-quote-form [name=basis]").selectOption("fixed");
  await page.locator("#market-quote-form [name=term_days]").fill("1095");
  await page
    .locator("#market-quote-form [name=source_url]")
    .fill("https://example.test/insurance-quote");
  await page
    .locator("#market-quote-form [name=coverage]")
    .fill("Comparable property coverage with matching deductible");
  await expect(page.locator("#market-quote-annual")).toHaveText("0.2%");
  await page.locator("#market-quote-form button[type=submit]").click();
  await expect(page.locator("#toast")).toHaveText("Market quote saved");
  await page.locator("[data-tab=templates]").click();
  await expect(page.locator("#source-coverage")).toContainText(
    "Available for the class",
  );

  await page.locator("[data-nav=surveys]").click();
  await page.locator("#new-survey").click();
  await page
    .locator("[name=title]")
    .fill("Document dates and sourced valuation");
  await page.locator("#create-survey button[type=submit]").click();
  await page.locator("#upload-form input").setInputFiles({
    name: "bureau-and-contract.txt",
    mimeType: "text/plain",
    buffer: Buffer.from(
      "Contract\nInsured sum: 100,000,000\nObject value: 100,000,000\nStart date: 01.01.2024\nEnd date: 01.01.2027\nBureau score: 750 / 1000",
    ),
  });
  await page.locator("#upload-form button").click();
  await expect(page.locator(".file-card")).toContainText(
    "bureau-and-contract.txt",
  );
  await page.locator("#to-review").click();
  await expect(page.locator("[name=insured_sum]")).toHaveValue("100000000");
  await expect(page.locator("[name=term_days]")).toHaveValue("1096");
  await page.locator("[name=product_code]").selectOption("DEMO-FIX");
  await page.locator("[name=object_type]").selectOption("housing");
  await page.locator("[name=borrower_enabled]").check();
  await page.locator("[name=borrower_organization_name]").fill("LLC Example");
  await page.locator("[name=borrower_bureau_name]").fill("Example bureau");
  await page
    .locator("[name=borrower_document_id]")
    .selectOption({ label: "bureau-and-contract.txt" });
  await page.locator("[name=borrower_report_date]").fill("2025-12-31");
  await page.locator("[name=borrower_score]").fill("750");
  await page.locator("[name=borrower_score_scale]").fill("0-1000");
  for (const price of [90000000, 110000000]) {
    await page.locator("#add-comparable").click();
    const comparable = page.locator(".comparable").last();
    await comparable.locator('[data-key="label"]').fill("Comparable housing");
    await comparable.locator('[data-key="price"]').fill(String(price));
    await comparable
      .locator('[data-key="date"]')
      .fill(new Date().toLocaleDateString("en-CA"));
    await comparable
      .locator('[data-key="source"]')
      .fill("https://example.test/listing");
  }
  await page.setViewportSize({ width: 390, height: 844 });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBeTruthy();
  await page.screenshot({
    path: "artifacts/gap-closure-review-mobile.png",
    fullPage: true,
  });
  await page.setViewportSize({ width: 1280, height: 900 });
  await page.locator("[name=manual_review_confirmed]").check();
  await page.locator("#review-form button[type=submit]").click();
  await expect(page.locator("#report-view")).toContainText(
    "Value range minimum, UZS: 90000000.00",
  );
  await expect(page.locator("#report-view")).toContainText(
    "Value range maximum, UZS: 110000000.00",
  );
  await expect(page.locator("#report-view")).toContainText("Bureau score: 750");
  await expect(page.locator("#report-view")).toContainText(
    "Original quoted rate, %: 0.6",
  );
  await page.screenshot({
    path: "artifacts/gap-closure-report.png",
    fullPage: true,
  });
  await require("./policy.cjs")(page);
  await require("./codex-pilot.cjs")(page);
  await require("./inspection-ai.cjs")(page);
  await require("./assistant.cjs")(page);
  await require("./telegram-downloads.cjs")(page);
  await require("./factor-pricing.cjs")(page);
  expect(errors).toEqual([]);
});
