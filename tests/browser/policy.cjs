const { expect } = require("@playwright/test");

module.exports = async function verifyPolicy(page) {
  await page.locator("#locale").selectOption("ru");
  await page.locator("[data-nav=policy]").click();
  await expect(page.locator("#catalog-count")).toHaveText("179 / 179");
  await page.locator("[name=policy_search]").fill("0309");
  await expect(page.locator("#catalog-rows tr")).toHaveCount(1);
  await page.locator('[data-policy="0309"]').click();
  await page
    .locator("#policy-check-form [name=variant]")
    .selectOption("legal_entity");
  await page.locator("#policy-check-form [name=rate]").fill("1.2");
  await page.locator("#policy-check-form [name=commission]").fill("26");
  await page.locator("#policy-check-form button[type=submit]").click();
  await expect(page.locator("#policy-check-result")).toContainText(
    "✕ Минимальный тариф",
  );
  await expect(page.locator("#policy-check-result")).toContainText(
    "✕ Лимит агентского вознаграждения",
  );
  await page
    .locator("#policy-check-form [name=variant]")
    .selectOption("individual");
  await page.locator("#policy-check-form [name=commission]").fill("25");
  await page.locator("#policy-check-form button[type=submit]").click();
  await expect(page.locator("#policy-check-result")).toContainText(
    "✓ Минимальный тариф",
  );
  await page.locator("#configure-policy").click();
  await expect(page.locator("#product-form [name=rate]")).toHaveValue("");
  await expect(page.locator("#product-form [name=effective_from]")).toHaveValue(
    "",
  );
  await page
    .locator("#product-form [name=policy_variant]")
    .selectOption("individual");
  await expect(page.locator("#product-form [name=min_rate]")).toHaveValue(
    "1.2",
  );
  await page.locator("#product-form [name=rate]").fill("1.4");
  await page.locator("#product-form [name=effective_from]").fill("2026-01-01");
  await page.locator("#product-form [name=rate_type]").selectOption("fixed");
  await page
    .locator("#product-form [name=policy_basis_reference]")
    .fill("Тест: ставка за договор, учебный приказ");
  await page
    .locator("#product-form [name=policy_terms_reference]")
    .fill("Тест: учебная программа KASKO");
  await page.locator("#product-form [name=policy_current_confirmed]").check();
  await page.locator("#product-form button[type=submit]").click();
  await expect(page.locator("#modal")).not.toBeVisible();
  await page.locator("[data-nav=admin]").click();
  await expect(page.locator("#admin-content")).toContainText("0309");
  await page.locator("[data-nav=policy]").click();
  await page.locator("#rnp-form [name=rnp_class]").selectOption("16");
  await page.locator("#rnp-form [name=rnp_crop]").selectOption("true");
  await page.locator("#rnp-form button[type=submit]").click();
  await expect(page.locator("#rnp-result")).toContainText("Учётная группа: 4");
  await page.locator("[name=policy_search]").fill("0305");
  await page.locator('[data-policy="0305"]').click();
  await expect(page.locator("#configure-policy")).toHaveCount(0);
  await page.locator("[name=component_vehicle]").fill("1.1");
  await page.locator("[name=component_accident]").fill("0.5");
  await page.locator("[name=component_liability]").fill("1");
  await page.locator("#policy-check-form button[type=submit]").click();
  await expect(page.locator("#policy-check-result .notice")).toHaveCount(3);
  await page.locator("#modal-close").click();
  await page.screenshot({
    path: "artifacts/policy-desktop.png",
    fullPage: true,
  });
  await page.setViewportSize({ width: 390, height: 844 });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBeTruthy();
  await page.screenshot({
    path: "artifacts/policy-mobile.png",
    fullPage: true,
  });
  await page.setViewportSize({ width: 1280, height: 900 });
};
