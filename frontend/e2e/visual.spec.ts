import { expect, test } from "@playwright/test";
import { installTask21Routes } from "./support/task21-fixtures";

const surfaces = [
  ["home", "/"],
  ["create", "/create"],
  ["cookbook", "/cookbook"],
  ["settings", "/settings"],
  ["unknown", "/not-found"],
] as const;

test.describe("Task21 visual candidate surfaces", () => {
  test.beforeEach(async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.emulateMedia({ reducedMotion: "reduce", colorScheme: "light" });
    await installTask21Routes(page);
  });

  for (const [name, path] of surfaces) {
    test(`${name} is stable at the 1440 desktop baseline`, async ({ page }, testInfo) => {
      await page.goto(path, { waitUntil: "networkidle" });
      await expect(page.locator("h1")).toHaveCount(1);
      await expect(page.locator("body")).toHaveCSS("overflow-x", "visible");
      const width = await page.evaluate(() => ({
        scrollWidth: document.documentElement.scrollWidth,
        clientWidth: document.documentElement.clientWidth,
      }));
      expect(width.scrollWidth).toBeLessThanOrEqual(width.clientWidth);
      await page.screenshot({
        path: testInfo.outputPath(`task21-candidate-${name}.png`),
        fullPage: true,
      });
    });
  }

  test("home keeps creation actions outside the banner and uses game glyphs", async ({ page }) => {
    await page.goto("/", { waitUntil: "networkidle" });
    await expect(page.locator(".hero-media .hero-copy")).toHaveCount(0);
    await expect(page.locator(".hero-copy--standalone")).toBeVisible();
    await expect(page.locator(".specific-icon--createFirstDish")).toBeVisible();
    await expect(page.locator(".specific-icon--blueprint")).toBeVisible();
    await expect(page.locator('.mode-card img[src="/assets/ui/gus-portrait-2.png"]')).toBeVisible();
    await expect(page.locator(".feature-link .game-ui-icon--collections")).toBeVisible();
    await expect(page.locator(".feature-link .game-ui-icon--gift")).toBeVisible();
  });

  test("cookbook removes the misleading capacity counter and uses the collection tab icon", async ({ page }) => {
    await page.goto("/cookbook", { waitUntil: "networkidle" });
    await expect(page.locator(".cookbook-heading .game-ui-icon--collections")).toBeVisible();
    await expect(page.locator(".field-counter")).toHaveCount(0);
    await expect(page.getByText(/\/\s*24/)).toHaveCount(0);
  });

  test("cookbook detail gives the preview column desktop reading room", async ({ page }) => {
    await page.goto("/cookbook/dish-1", { waitUntil: "networkidle" });
    const columns = await page.locator(".detail-layout").evaluate((element) => {
      const styles = getComputedStyle(element);
      return styles.gridTemplateColumns;
    });
    const firstColumn = Number.parseFloat(columns.split(" ")[0] ?? "0");
    expect(firstColumn).toBeGreaterThan(500);
    await expect(page.locator(".detail-visual-panel .detail-preview img")).toBeVisible();
  });

  test("Gus result preview preserves the returned image instead of cropping it", async ({ page }) => {
    await page.goto("/drafts/ask-gus", { waitUntil: "networkidle" });
    const preview = page.locator(".gus-preview__main img");
    await expect(preview).toBeVisible();
    const styles = await preview.evaluate((element) => {
      const image = element as HTMLImageElement;
      const computed = getComputedStyle(image);
      return {
        objectFit: computed.objectFit,
        maxHeight: computed.maxHeight,
        height: computed.height,
        naturalWidth: image.naturalWidth,
        naturalHeight: image.naturalHeight,
      };
    });
    expect(styles.objectFit).toBe("contain");
    expect(styles.maxHeight).toBe("none");
    expect(styles.naturalWidth).toBeGreaterThan(0);
    expect(styles.naturalHeight).toBeGreaterThan(0);
  });

  test("1024 desktop remains horizontally usable", async ({ page }) => {
    await page.setViewportSize({ width: 1024, height: 768 });
    await page.goto("/create", { waitUntil: "networkidle" });
    const width = await page.evaluate(() => ({
      scrollWidth: document.documentElement.scrollWidth,
      clientWidth: document.documentElement.clientWidth,
    }));
    expect(width.scrollWidth).toBeLessThanOrEqual(width.clientWidth);
    await expect(page.getByRole("button", { name: "创建草稿" })).toBeDisabled();
  });

  test("cookbook selection swaps the preview and opens the matching detail page", async ({ page }) => {
    await page.goto("/cookbook", { waitUntil: "networkidle" });
    await expect(page.getByRole("img", { name: "番茄酱汁煎鲑鱼预览" })).toBeVisible();

    await page.getByRole("button", { name: "查看菠菜烟熏三文鱼预览" }).click();
    await expect(page.getByRole("img", { name: "菠菜烟熏三文鱼预览" })).toBeVisible();
    await expect(page.getByRole("link", { name: "查看完整菜品 →" })).toHaveAttribute(
      "href",
      "/cookbook/dish-2",
    );

    await page.getByRole("link", { name: "查看完整菜品 →" }).click();
    await page.waitForURL("**/cookbook/dish-2");
    await expect(page.locator("h1")).toHaveText("菠菜烟熏三文鱼");
  });

  test("core draft and derived surfaces produce candidate captures", async ({ page }, testInfo) => {
    for (const [name, path] of [
      ["gus-reviewable", "/drafts/ask-gus"],
      ["blueprint-stale", "/drafts/blueprint"],
      ["cookbook-detail", "/cookbook/dish-1"],
      ["bring-in-game", "/bring-in-game/export-1"],
    ] as const) {
      await page.goto(path, { waitUntil: "networkidle" });
      await expect(page.locator("h1:visible")).toHaveCount(1);
      await page.screenshot({
        path: testInfo.outputPath(`task21-candidate-${name}.png`),
        fullPage: true,
      });
    }

    await page.goto("/cookbook", { waitUntil: "networkidle" });
    for (const checkbox of await page.getByRole("checkbox").all()) {
      if (await checkbox.isVisible()) {
        await checkbox.check();
        if (await page.locator("input[type=checkbox]:checked").count() === 3) {
          break;
        }
      }
    }
    await page.getByRole("button", { name: "打包菜单" }).click();
    await page.waitForURL("**/pack-menu");
    await page.screenshot({
      path: testInfo.outputPath("task21-candidate-pack-menu.png"),
      fullPage: true,
    });
  });
});
