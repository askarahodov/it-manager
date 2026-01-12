import { test, expect } from "@playwright/test";

import { ensureDemoHostWithSecret, loginAsAdmin } from "./_helpers";

test("terminal: вкладка Terminal в карточке хоста принимает команды", async ({ page }) => {
  await loginAsAdmin(page);

  await page.getByRole("button", { name: "Хосты" }).click();
  await expect(page.getByRole("heading", { name: "Хосты" })).toBeVisible();

  const demoHost = await ensureDemoHostWithSecret(page);
  await page.getByLabel("Поиск по name/hostname").fill(demoHost.name);
  await page.getByRole("button", { name: "Обновить" }).click();
  await expect(page.locator("tr", { hasText: demoHost.name }).first()).toBeVisible();

  await page.locator("tr", { hasText: demoHost.name }).first().getByRole("button", { name: "Детали" }).click();
  await expect(page.getByRole("heading", { name: new RegExp(`^Хост: ${demoHost.name}$`) })).toBeVisible();

  const terminalTab = page.getByRole("button", { name: "Вкладка: терминал" });
  await expect(terminalTab).toBeEnabled();
  await terminalTab.click();
  await expect(page.getByText(/Статус:\s*(connected|connecting)/i)).toBeVisible();

  // Дадим ssh несколько секунд показать приветствие/промпт.
  const rows = page.locator(".xterm-rows");
  await expect(rows).toBeVisible();

  await page.locator(".terminal-container").click();
  await page.keyboard.type("whoami");
  await page.keyboard.press("Enter");

  await expect(rows).toContainText(/demo/);
});
