import fs from "fs";
import path from "path";

import { expect, Page } from "@playwright/test";

function runId(): string {
  // Стабильный id для одного процесса прогона, чтобы сравнивать "до/после".
  const fromEnv = process.env.E2E_RUN_ID?.trim();
  if (fromEnv) return fromEnv;
  const d = new Date();
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}${pad(d.getMonth() + 1)}${pad(d.getDate())}-${pad(d.getHours())}${pad(d.getMinutes())}${pad(d.getSeconds())}`;
}

async function getToken(page: Page): Promise<string> {
  const token = await page.evaluate(() => localStorage.getItem("it_manager_token"));
  if (!token) throw new Error("E2E: token отсутствует в localStorage после логина");
  return token;
}

export async function loginAsAdmin(page: Page) {
  await page.goto("/");
  // На старте обычно активна Settings (если нет токена), но на всякий случай кликнем.
  await page.getByRole("button", { name: "Настройки" }).click();
  await page.getByRole("heading", { name: "Настройки" }).waitFor();
  // Если уже залогинены (например, сохранился токен в localStorage), ничего не делаем.
  if (await page.getByText(/Вы вошли как/i).isVisible().catch(() => false)) return;
  await page.getByLabel("Email").fill(process.env.E2E_ADMIN_EMAIL || "admin@it.local");
  await page.getByLabel("Пароль").fill(process.env.E2E_ADMIN_PASSWORD || "admin123");
  await page.getByRole("button", { name: "Войти" }).click();
  await expect(page.getByText(/Вы вошли как/i)).toBeVisible();
}

export async function ensureDemoHostWithSecret(page: Page) {
  const token = await getToken(page);
  const id = `${runId()}-${Math.random().toString(16).slice(2, 8)}`;
  const secretName = `e2e-secret-${id}`;
  const hostName = `e2e-host-${id}`;

  const secretResp = await page.request.post("/api/v1/secrets/", {
    headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
    data: {
      name: secretName,
      type: "password",
      scope: "global",
      description: "e2e",
      tags: { e2e: "1" },
      value: "demo123",
    },
  });
  expect(secretResp.ok(), await secretResp.text()).toBeTruthy();
  const secret = (await secretResp.json()) as { id: number };

  const hostResp = await page.request.post("/api/v1/hosts/", {
    headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
    data: {
      name: hostName,
      hostname: "ssh-demo",
      port: 22,
      username: "demo",
      os_type: "linux",
      environment: "dev",
      tags: { e2e: "1" },
      description: "e2e",
      credential_id: secret.id,
      check_method: "ssh",
    },
  });
  expect(hostResp.ok(), await hostResp.text()).toBeTruthy();
  const host = (await hostResp.json()) as { id: number; name: string };

  // Обновим статус, чтобы UI мог корректно разрешать "Терминал" (online/offline).
  const startedAt = Date.now();
  while (true) {
    const statusResp = await page.request.post(`/api/v1/hosts/${host.id}/status-check`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    expect(statusResp.ok(), await statusResp.text()).toBeTruthy();
    const body = (await statusResp.json()) as { status?: string };
    if (body?.status === "online") break;
    if (Date.now() - startedAt > 20_000) break;
    await page.waitForTimeout(1000);
  }
  return host;
}

export async function takeScreenshot(page: Page, name: string) {
  const base = path.join(process.cwd(), "e2e-artifacts", "screenshots");
  const currentRun = runId();
  const latestDir = path.join(base, "latest");
  const runDir = path.join(base, currentRun);
  fs.mkdirSync(latestDir, { recursive: true });
  fs.mkdirSync(runDir, { recursive: true });

  const latestFile = path.join(latestDir, `${name}.png`);
  const runFile = path.join(runDir, `${name}.png`);

  await page.screenshot({ path: runFile, fullPage: true });
  fs.copyFileSync(runFile, latestFile);
  return runFile;
}
