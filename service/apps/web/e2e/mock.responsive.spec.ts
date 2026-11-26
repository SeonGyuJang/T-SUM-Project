import { expect, test } from "@playwright/test";

test("모바일에서 가로 스크롤 없이 핵심 화면이 보인다", async ({ page }) => {
  for (const path of ["/", "/analyze", "/check", "/how-it-works", "/analyses/mock-vacuum"]) {
    await page.goto(path);
    await expect(page.locator("h1").first()).toBeVisible();
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
    expect(overflow, path).toBeLessThanOrEqual(1);
  }
});
