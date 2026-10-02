const { expect } = require("@playwright/test");
module.exports = async (page) => {
  await page.locator("#locale").selectOption("ru");
  await page.locator("[data-nav=admin]").click();
  await page.locator("[data-tab=templates]").click();
  const vehicle = page
    .locator(".file-card")
    .filter({ has: page.locator("h3", { hasText: "Автотранспорт" }) });
  await vehicle.locator("[data-factor-policy]").click();
  await page
    .locator("#factor-policy-form [name=rationale]")
    .fill("Вымышленная настройка для функциональной проверки");
  await page.locator('[data-coefficient="factor_001"] summary').click();
  await page.locator("[name=raises_factor_001]").fill("1.2");
  await page.locator("#factor-policy-form button[type=submit]").click();
  await expect(vehicle).toContainText("Не калибровано");
  await vehicle.locator("[data-factor-experience]").click();
  const year = new Date().getFullYear();
  const csv =
    "factor_id,choice,year,exposure,claims,payments\n" +
    Array.from(
      { length: 3 },
      (_, i) =>
        `${"factor_001"},neutral,${year - 3 + i},100,10,1000\nfactor_001,raises,${year - 3 + i},100,15,1500`,
    ).join("\n");
  await page.locator("#factor-experience-form input").setInputFiles({
    name: "fictional-factor-experience.csv",
    mimeType: "text/csv",
    buffer: Buffer.from(csv),
  });
  await page.locator("#factor-experience-form button").click();
  await page.locator("#confirm-factor-experience").click();
  await expect(page.locator("#modal-content")).toContainText("SHA256:");
  await page.locator("#modal-close").click();
  // Create a separate fictional actuary; use actual auth and forced-password-change APIs.
  await page.evaluate(async () => {
    await post("/admin/employees", {
      login: "factor-actuary",
      password: "fictional-factor-initial",
      phone: "+998900009876",
      name: "Fictional factor actuary",
      role: "actuary",
    });
    const auth = await post("/auth/login", {
      login: "factor-actuary",
      password: "fictional-factor-initial",
    });
    state.csrf = auth.csrf;
    await post("/auth/password", {
      old_password: "fictional-factor-initial",
      new_password: "fictional-factor-changed",
    });
  });
  await page.reload();
  await page.locator("[data-nav=admin]").click();
  await page.locator("[data-tab=templates]").click();
  await vehicle.locator("[data-factor-experience]").click();
  await page.locator("[name=minimum_exposure]").fill("100");
  await page.locator("[name=max_change]").fill("0.2");
  await page
    .locator("#factor-calibration-form [name=rationale]")
    .fill("Вымышленная проверка метода и сопоставимости сегментов");
  await page.locator("[name=method_confirmed]").check();
  await page.locator("#factor-calibration-form button").click();
  await expect(vehicle).toContainText("Статистическое предложение");
  await vehicle.locator("[data-approve-template]").click();
  await expect(vehicle).toContainText("Утверждён актуарием");
  await page.locator("[data-nav=surveys]").click();
  await page.locator("#new-survey").click();
  await page
    .locator("[name=title]")
    .fill("FICTIONAL · full factor pricing browser acceptance");
  await page.locator("#create-survey button[type=submit]").click();
  await page.locator("#to-review").click();
  await page.locator("[name=product_code]").selectOption("DEMO-AUTO");
  await page.locator("[name=insured_sum]").fill("100000000");
  await page.locator("[name=object_value]").fill("100000000");
  await page.locator("[name=language]").selectOption("ru");
  const first = page.locator('[data-factor="factor_001"]');
  await first.locator("summary").click();
  await first.locator("select").selectOption("raises");
  await first
    .locator("textarea")
    .fill("Вымышленная история убытков; проверено сотрудником");
  await page.setViewportSize({ width: 390, height: 844 });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBeTruthy();
  await page.locator("[name=manual_review_confirmed]").check();
  await page.locator("#review-form button[type=submit]").click();
  await expect(page.locator("#report-view")).toContainText("Уточнить факторы");
  await expect(page.locator("#report-view")).toContainText(
    "Применённое произведение: 1.20000000",
  );
  await expect(page.locator("#report-view")).toContainText("600000.00");
  for (const format of ["PDF", "Word"]) {
    const event = page.waitForEvent("download");
    await page.getByRole("link", { name: `↓ ${format}` }).click();
    const file = await event;
    expect(await file.failure()).toBeNull();
  }
  await page.screenshot({
    path: "artifacts/factor-pricing-mobile.png",
    fullPage: true,
  });
  await page.locator("[data-nav=calculator]").click();
  await page.locator("[name=product_code]").selectOption("DEMO-AUTO");
  await page.locator("[name=insured_sum]").fill("100000000");
  await page.locator("[name=object_value]").fill("100000000");
  const calcFactor = page.locator(
    '#calculator-factors [data-factor="factor_001"]',
  );
  await calcFactor.locator("summary").click();
  await calcFactor.locator("select").selectOption("raises");
  await calcFactor
    .locator("textarea")
    .fill("Вымышленная проверка калькулятора");
  await page.locator("#calculator-form button[type=submit]").click();
  await expect(page.locator("#calculator-result .result-value")).toContainText(
    "600",
  );
  await expect(page.locator("#calculator-result")).toContainText("1.20000000");
  await page.locator("#locale").selectOption("en");
  await expect(page.locator("#calculator-factors h3")).toHaveText(
    "Tariff factors",
  );
  await expect(page.locator("[name=product_code]")).toHaveValue("DEMO-AUTO");
  await expect(page.locator("[name=insured_sum]")).toHaveValue("100000000");
  await expect(calcFactor.locator("select")).toHaveValue("raises");
  await expect(calcFactor.locator("textarea")).toHaveValue(
    "Вымышленная проверка калькулятора",
  );
  await page.locator("#locale").selectOption("uz");
  await expect(page.locator("#calculator-factors h3")).toHaveText(
    "Tarif omillari",
  );
};
