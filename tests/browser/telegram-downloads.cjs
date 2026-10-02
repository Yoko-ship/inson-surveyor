const { expect } = require("@playwright/test");

module.exports = async (page) => {
  // The signed-link route is covered by Python security tests; emulate the
  // Telegram host bridge here because browser CI has no Telegram account.
  await page.locator("[data-step=report]").click();
  await expect(page.locator("[data-report-export=pdf]")).toBeVisible();
  const originalHref = await page
    .locator("[data-report-export=pdf]")
    .getAttribute("href");
  const reportId = originalHref.split("/")[3];
  await page.route("**/api/reports/*/export/*/download-link", async (route) => {
    expect(route.request().method()).toBe("POST");
    expect(route.request().headers()["x-csrf-token"]).toBeTruthy();
    const format = new URL(route.request().url()).pathname.split("/")[5];
    await route.fulfill({
      json: {
        url: `https://example.test/download/${format}`,
        file_name: `surveyor-${reportId}.${format}`,
        expires_in: 300,
      },
    });
  });
  await page.evaluate(() => {
    window.downloadRequests = [];
    window.openedDownloads = [];
    window.Telegram = {
      WebApp: {
        initData: "test-telegram-launch",
        isVersionAtLeast: () => true,
        downloadFile: (file) => window.downloadRequests.push(file),
        openLink: (url) => window.openedDownloads.push(url),
      },
    };
  });
  for (const format of ["pdf", "docx"]) {
    await page.locator(`[data-report-export=${format}]`).click();
    await expect
      .poll(() => page.evaluate(() => window.downloadRequests.length))
      .toBe(format === "pdf" ? 1 : 2);
  }
  expect(await page.evaluate(() => window.downloadRequests)).toEqual([
    {
      url: "https://example.test/download/pdf",
      file_name: `surveyor-${reportId}.pdf`,
    },
    {
      url: "https://example.test/download/docx",
      file_name: `surveyor-${reportId}.docx`,
    },
  ]);
  // Old clients require a separate user click to open an external browser.
  await page.evaluate(() => {
    window.Telegram.WebApp.isVersionAtLeast = () => false;
  });
  await page.locator("[data-report-export=pdf]").click();
  await expect(page.locator("#open-report-file")).toBeVisible();
  expect(await page.evaluate(() => window.openedDownloads)).toEqual([]);
  await page.locator("#open-report-file").click();
  expect(await page.evaluate(() => window.openedDownloads)).toEqual([
    "https://example.test/download/pdf",
  ]);
  await page.locator("#modal-close").click();
  await page.evaluate(() => {
    window.Telegram.WebApp.initData = "";
  });
  await page.unroute("**/api/reports/*/export/*/download-link");
};
