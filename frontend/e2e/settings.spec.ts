import { expect, test, type Page, type Route } from "@playwright/test";

/**
 * Trial-entry E2E (Task 30).
 *
 * Covers the Settings trial panel's states with route interception:
 *   - available + disabled -> "不想配置，先试试效果" enable button
 *   - enabled + quota left -> "试用模式已开启，还可生成 X 次" + "退出试用"
 *   - enabled + exhausted  -> "你已经达到试用额度，请配置自己的服务"
 *   - missing key resource -> "试用功能暂时不可用，请配置自己的服务"
 *   - configured user (R-09) -> priority status, no opt-in button
 *
 * Every API call is intercepted with page.route; no backend process and no
 * model call is involved.
 */

const CSRF = "e2e-csrf-token";

type TrialStatus = {
  available: boolean;
  enabled: boolean;
  claimedAttempts: number;
  limit: number;
  remaining: number;
};

function trialStatus(overrides: Partial<TrialStatus> = {}): TrialStatus {
  return {
    available: true,
    enabled: false,
    claimedAttempts: 0,
    limit: 2,
    remaining: 2,
    ...overrides,
  };
}

const settingsView = {
  providerKind: "OPENAI_COMPATIBLE",
  baseUrl: "https://yibuapi.com/v1",
  visionModel: "vision-model",
  textModel: "text-model",
  imageModel: "image-model",
  chatTimeoutSeconds: 120,
  imageTimeoutSeconds: 300,
  maxAutomaticRetries: 2,
  apiKeyConfigured: false,
  apiKeySource: "ENVIRONMENT",
};

async function installSettingsRoutes(
  page: Page,
  state: { trial: TrialStatus; configured?: boolean },
): Promise<void> {
  const configured = state.configured ?? false;
  await page.route("/session/bootstrap", (route: Route) => {
    void route.fulfill({ status: 204, headers: { "X-PTS-CSRF": CSRF } });
  });
  await page.route("/session/status", (route: Route) => {
    void route.fulfill({ status: 200, headers: { "X-PTS-CSRF": CSRF }, body: "" });
  });
  await page.route("/app/heartbeat", (route: Route) => {
    void route.fulfill({ status: 204 });
  });
  await page.route("/api/v1/health", (route: Route) => {
    void route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ status: "ok", app: "PelicanTownSpecials", apiVersion: "v1" }),
    });
  });
  await page.route("/api/v1/settings/provider", (route: Route) => {
    void route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ ...settingsView, apiKeyConfigured: configured }),
    });
  });
  await page.route("/api/v1/settings/provider/key", (route: Route) => {
    void route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ apiKeyConfigured: true, apiKeySource: "ENVIRONMENT" }),
    });
  });
  await page.route("/api/v1/settings/provider/trial", (route: Route) => {
    const method = route.request().method();
    if (method === "POST") {
      state.trial = trialStatus({ ...state.trial, enabled: true });
    } else if (method === "DELETE") {
      state.trial = trialStatus({ ...state.trial, enabled: false });
    }
    void route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(state.trial),
    });
  });
}

test.describe("settings trial entry", () => {
  test("enables the trial, shows the quota status, then exits", async ({ page }) => {
    const state = { trial: trialStatus() };
    await installSettingsRoutes(page, state);

    await page.goto("/settings", { waitUntil: "networkidle" });
    await expect(page.getByRole("heading", { name: "试用模式" })).toBeVisible();
    await expect(
      page.getByRole("button", { name: "不想配置，先试试效果" }),
    ).toBeVisible();

    await page.getByRole("button", { name: "不想配置，先试试效果" }).click();
    await expect(page.getByText("试用模式已开启，还可生成 2 次")).toBeVisible();
    await expect(page.getByRole("button", { name: "退出试用" })).toBeVisible();

    await page.getByRole("button", { name: "退出试用" }).click();
    await expect(
      page.getByRole("button", { name: "不想配置，先试试效果" }),
    ).toBeVisible();
  });

  test("shows the exhausted hint when the trial quota is used up", async ({ page }) => {
    const state = {
      trial: trialStatus({ enabled: true, claimedAttempts: 2, remaining: 0 }),
    };
    await installSettingsRoutes(page, state);

    await page.goto("/settings", { waitUntil: "networkidle" });

    await expect(page.getByText("你已经达到试用额度，请配置自己的服务")).toBeVisible();
    await expect(page.getByRole("button", { name: "退出试用" })).toBeVisible();
  });

  test("shows the unavailable hint when the trial key resource is missing", async ({ page }) => {
    const state = { trial: trialStatus({ available: false }) };
    await installSettingsRoutes(page, state);

    await page.goto("/settings", { waitUntil: "networkidle" });

    await expect(
      page.getByText("试用功能暂时不可用，请配置自己的服务"),
    ).toBeVisible();
    await expect(
      page.getByRole("button", { name: "不想配置，先试试效果" }),
    ).toHaveCount(0);
  });

  test("configured user sees the priority status and no opt-in button", async ({ page }) => {
    const state = { trial: trialStatus(), configured: true };
    await installSettingsRoutes(page, state);

    await page.goto("/settings", { waitUntil: "networkidle" });

    await expect(
      page.getByText("个人服务已设置，将优先使用 2 次试用额度"),
    ).toBeVisible();
    await expect(
      page.getByRole("button", { name: "不想配置，先试试效果" }),
    ).toHaveCount(0);
  });
});
