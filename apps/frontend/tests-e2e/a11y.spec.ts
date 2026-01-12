import { test, expect } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

import { ensureDemoHostWithSecret, loginAsAdmin } from "./_helpers";

async function expectNoCriticalA11yViolations(page: any) {
  const results = await new AxeBuilder({ page }).analyze();
  const critical = results.violations.filter((v: any) => v.impact === "critical" || v.impact === "serious");
  expect(critical, `Найдены a11y проблемы critical/serious: ${JSON.stringify(critical, null, 2)}`).toEqual([]);
}

test("a11y: Settings/Hosts/Secrets", async ({ page }) => {
  await loginAsAdmin(page);
  await expectNoCriticalA11yViolations(page);

  await page.getByRole("button", { name: "Хосты" }).click();
  await expect(page.getByRole("heading", { name: "Хосты" })).toBeVisible();
  await expectNoCriticalA11yViolations(page);

  const demoHost = await ensureDemoHostWithSecret(page);
  await page.getByLabel("Поиск по name/hostname").fill(demoHost.name);
  await page.getByRole("button", { name: "Обновить" }).click();
  await expect(page.locator("tr", { hasText: demoHost.name }).first()).toBeVisible();
  await page.locator("tr", { hasText: demoHost.name }).first().getByRole("button", { name: "Детали" }).click();
  await expect(page.getByRole("heading", { name: new RegExp(`^Хост: ${demoHost.name}$`) })).toBeVisible();
  await expectNoCriticalA11yViolations(page);
  await page.getByRole("button", { name: "Назад" }).click();

  await page.getByRole("button", { name: "Секреты" }).click();
  await expect(page.getByRole("heading", { name: "Секреты" })).toBeVisible();
  await expectNoCriticalA11yViolations(page);
});
