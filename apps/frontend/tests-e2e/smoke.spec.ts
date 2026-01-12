import { test, expect } from "@playwright/test";

import { ensureDemoHostWithSecret, loginAsAdmin, takeScreenshot } from "./_helpers";

test("smoke: логин и навигация по ключевым разделам", async ({ page }) => {
  await loginAsAdmin(page);
  await takeScreenshot(page, "01-settings-authenticated");

  await page.getByRole("button", { name: "Хосты" }).click();
  await expect(page.getByRole("heading", { name: "Хосты" })).toBeVisible();
  const demoHost = await ensureDemoHostWithSecret(page);
  await page.getByLabel("Поиск по name/hostname").fill(demoHost.name);
  await page.getByRole("button", { name: "Обновить" }).click();
  await expect(page.locator("tr", { hasText: demoHost.name }).first()).toBeVisible();
  await takeScreenshot(page, "02-hosts");

  await page.locator("tr", { hasText: demoHost.name }).first().getByRole("button", { name: "Детали" }).click();
  await expect(page.getByRole("heading", { name: new RegExp(`^Хост: ${demoHost.name}$`) })).toBeVisible();
  await takeScreenshot(page, "02b-host-details");
  await page.getByRole("button", { name: "Назад" }).click();
  await expect(page.getByRole("heading", { name: "Хосты" })).toBeVisible();

  await page.getByRole("button", { name: "Секреты" }).click();
  await expect(page.getByRole("heading", { name: "Секреты" })).toBeVisible();
  await takeScreenshot(page, "03-secrets");

  await page.getByRole("button", { name: "Группы" }).click();
  await expect(page.getByRole("heading", { name: "Группы" })).toBeVisible();
  await takeScreenshot(page, "04-groups");

  await page.getByRole("button", { name: "Автоматизация" }).click();
  await expect(page.getByRole("heading", { name: "Плейбуки и запуски" })).toBeVisible();
  await takeScreenshot(page, "05-automation");
});
