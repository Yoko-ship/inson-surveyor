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
  await page
    .locator("#upload-form input")
    .setInputFiles({
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
  expect(errors).toEqual([]);
});
