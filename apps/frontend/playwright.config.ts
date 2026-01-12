import path from "path";

import { defineConfig, devices } from "@playwright/test";

function ensureNoProxyForLocalhost() {
  const defaults = ["127.0.0.1", "localhost"];
  const current = (process.env.NO_PROXY || process.env.no_proxy || "").trim();
  const items = current
    ? current.split(",").map((x) => x.trim()).filter(Boolean)
    : [];
  for (const d of defaults) {
    if (!items.includes(d)) items.push(d);
  }
  const value = items.join(",");
  process.env.NO_PROXY = value;
  process.env.no_proxy = value;
}

ensureNoProxyForLocalhost();
// По умолчанию используем системный кеш Playwright.
// При необходимости можно хранить браузеры в репозитории (удобно для изолированных окружений),
// включив флаг: E2E_BROWSERS_IN_REPO=1.
if (process.env.E2E_BROWSERS_IN_REPO === "1") {
  process.env.PLAYWRIGHT_BROWSERS_PATH ||= path.join(__dirname, ".pw-browsers");
}

export default defineConfig({
  testDir: "./tests-e2e",
  timeout: 60_000,
  expect: { timeout: 10_000 },
  retries: process.env.CI ? 1 : 0,
  reporter: [
    ["list"],
    ["html", { open: "never" }],
  ],
  outputDir: "test-results",
  use: {
    baseURL: process.env.E2E_BASE_URL || "http://127.0.0.1:4173",
    trace: (process.env.E2E_TRACE as any) || "on-first-retry",
    video: (process.env.E2E_VIDEO as any) || "retain-on-failure",
    screenshot: (process.env.E2E_SCREENSHOT as any) || "only-on-failure",
    actionTimeout: 15_000,
    navigationTimeout: 30_000,
  },
  webServer: {
    command: "bash scripts/e2e-webserver.sh",
    url: (process.env.E2E_BASE_URL || "http://127.0.0.1:4173") + "/api/healthz",
    timeout: 600_000,
    // По умолчанию НЕ переиспользуем уже запущенный сервер: иначе легко поймать
    // "старую" сборку и получить неустойчивые результаты.
    // Для локальной отладки можно включить: E2E_REUSE_SERVER=1
    reuseExistingServer: process.env.E2E_REUSE_SERVER === "1",
    cwd: path.resolve(__dirname, "..", ".."),
  },
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
  ],
});
