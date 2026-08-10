import { expect, test } from "@playwright/test";
import { installTask21Routes } from "./support/task21-fixtures";

test.describe("Task21 keyboard and semantic smoke", () => {
  test.beforeEach(async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.emulateMedia({ reducedMotion: "reduce", colorScheme: "light" });
    await installTask21Routes(page);
  });

  test("skip link enters main and every core page has one h1", async ({ page }) => {
    for (const path of ["/", "/create", "/cookbook", "/settings", "/not-found"]) {
      await page.goto(path, { waitUntil: "networkidle" });
      await expect(page.locator("h1:visible")).toHaveCount(1);
    }
    await page.goto("/", { waitUntil: "networkidle" });
    await page.keyboard.press("Tab");
    await expect(page.locator(".skip-link")).toBeFocused();
    await page.keyboard.press("Enter");
    await expect(page.locator("#main-content")).toBeFocused();
  });

  test("create and settings controls expose labels", async ({ page }) => {
    await page.goto("/create", { waitUntil: "networkidle" });
    await expect(page.getByLabel("上传菜品照片")).toBeAttached();
    await expect(page.getByLabel("补充说明（可选）")).toBeAttached();

    await page.goto("/settings", { waitUntil: "networkidle" });
    for (const label of ["Base URL", "视觉模型 ID", "文本模型 ID", "图像模型 ID", "API Key"]) {
      if (label === "API Key") {
        await expect(page.getByRole("textbox", { name: label })).toBeAttached();
      } else {
        await expect(page.getByLabel(label)).toBeAttached();
      }
    }
  });

  test("home discard uses a named modal with Escape close", async ({ page }) => {
    await page.goto("/", { waitUntil: "networkidle" });
    await page.getByRole("button", { name: "放弃草稿" }).first().click();
    const dialog = page.getByRole("dialog", { name: "放弃这份草稿？" });
    await expect(dialog).toBeVisible();
    await expect(dialog.locator("button").first()).toBeFocused();
    await page.keyboard.press("Escape");
    await expect(dialog).toBeHidden();
  });

  test("generation stage output has no fabricated percentage", async ({ page }) => {
    await page.goto("/drafts/ask-gus", { waitUntil: "networkidle" });
    await expect(page.getByRole("heading", { name: "问问 Gus 审核" })).toBeVisible();
    await expect(page.locator("text=生成进度")).toHaveCount(0);
    await expect(page.locator("body")).not.toContainText(/\b\d+%\b/);
  });
});
