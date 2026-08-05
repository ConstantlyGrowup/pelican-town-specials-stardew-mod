import { expect, test, type Page, type Route } from "@playwright/test";

/**
 * Fake-flow E2E for the export experience. Every API call is intercepted with
 * page.route; no backend process is involved. The download is fulfilled with a
 * real (STORE-method) ZIP so the test can verify filename and structure.
 */

const CSRF = "e2e-csrf-token";
const PACK_SLUG = "FamilyMenu";
const ZIP_FILENAME = `[CP] Pelican Town Specials - ${PACK_SLUG}.zip`;
const PACK_ROOT = `[CP] Pelican Town Specials - ${PACK_SLUG}`;

const record = {
  exportId: "export-1",
  spec: {
    dishIds: ["dish-1"],
    packDisplayName: "家庭菜单",
    packSlug: PACK_SLUG,
    version: "1.0.0",
    description: "一份装满鹈鹕镇风味的菜单。",
    language: "zh-CN",
  },
  authorName: "D20260801",
  uniqueId: `D20260801.PelicanTownSpecials.${PACK_SLUG}`,
  status: "SUCCEEDED",
  dishContentHashes: { "dish-1": "a".repeat(64) },
  compilerVersion: "task16-export-compiler-v1",
  gameVersion: "1.6.15",
  contentPatcherFormat: "2.9.0",
  validation: {
    valid: true,
    issues: [],
    validatedAt: "2026-08-04T00:00:00Z",
    validatorVersion: "task16-export-validator-v1",
  },
  artifactAssetId: "00000000-0000-4000-8000-000000000004",
  createdAt: "2026-08-04T00:00:00Z",
  finishedAt: "2026-08-04T00:00:01Z",
  error: null,
};

function crc32(buffer: Buffer): number {
  let crc = 0xffffffff;
  for (let i = 0; i < buffer.length; i++) {
    crc ^= buffer[i];
    for (let j = 0; j < 8; j++) {
      crc = (crc >>> 1) ^ (0xedb88320 & -(crc & 1));
    }
  }
  return (crc ^ 0xffffffff) >>> 0;
}

function buildZip(entries: Record<string, Buffer>): Buffer {
  const chunks: Buffer[] = [];
  const central: Buffer[] = [];
  let offset = 0;
  const names = Object.keys(entries).sort();

  for (const name of names) {
    const data = entries[name];
    const nameBuf = Buffer.from(name, "utf-8");
    const crc = crc32(data);

    const local = Buffer.alloc(30);
    local.writeUInt32LE(0x04034b50, 0);
    local.writeUInt16LE(20, 4);
    local.writeUInt16LE(0, 6);
    local.writeUInt16LE(0, 8);
    local.writeUInt16LE(0, 10);
    local.writeUInt16LE(0, 12);
    local.writeUInt32LE(crc, 14);
    local.writeUInt32LE(data.length, 18);
    local.writeUInt32LE(data.length, 22);
    local.writeUInt16LE(nameBuf.length, 26);
    local.writeUInt16LE(0, 28);
    chunks.push(local, nameBuf, data);

    const cen = Buffer.alloc(46);
    cen.writeUInt32LE(0x02014b50, 0);
    cen.writeUInt16LE(20, 4);
    cen.writeUInt16LE(20, 6);
    cen.writeUInt16LE(0, 8);
    cen.writeUInt16LE(0, 10);
    cen.writeUInt16LE(0, 12);
    cen.writeUInt16LE(0, 14);
    cen.writeUInt32LE(crc, 16);
    cen.writeUInt32LE(data.length, 20);
    cen.writeUInt32LE(data.length, 24);
    cen.writeUInt16LE(nameBuf.length, 28);
    cen.writeUInt16LE(0, 30);
    cen.writeUInt16LE(0, 32);
    cen.writeUInt16LE(0, 34);
    cen.writeUInt16LE(0, 36);
    cen.writeUInt32LE(0, 38);
    cen.writeUInt32LE(offset, 42);
    central.push(cen, nameBuf);

    offset += 30 + nameBuf.length + data.length;
  }

  const centralSize = central.reduce((acc, buffer) => acc + buffer.length, 0);
  const eocd = Buffer.alloc(22);
  eocd.writeUInt32LE(0x06054b50, 0);
  eocd.writeUInt16LE(0, 4);
  eocd.writeUInt16LE(0, 6);
  eocd.writeUInt16LE(names.length, 8);
  eocd.writeUInt16LE(names.length, 10);
  eocd.writeUInt32LE(centralSize, 12);
  eocd.writeUInt32LE(offset, 16);
  eocd.writeUInt16LE(0, 20);

  return Buffer.concat([...chunks, ...central, eocd]);
}

async function installApiRoutes(page: Page): Promise<void> {
  await page.route("/session/bootstrap", (route: Route) => {
    void route.fulfill({ status: 204, headers: { "X-PTS-CSRF": CSRF } });
  });
  await page.route("/session/status", (route: Route) => {
    void route.fulfill({ status: 200, headers: { "X-PTS-CSRF": CSRF }, body: "" });
  });
  await page.route("/api/v1/health", (route: Route) => {
    void route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        status: "ok",
        app: "PelicanTownSpecials",
        apiVersion: "v1",
      }),
    });
  });
  await page.route("/api/v1/cookbook", (route: Route) => {
    void route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        items: [
          {
            dishId: "dish-1",
            archivedAt: "2026-08-04T00:00:00Z",
            displayName: "番茄炖菜",
            categoryLabel: "主菜",
            description: "慢炖番茄与欧防风，暖胃又满足。",
            tags: ["stew"],
          },
        ],
        nextCursor: null,
        total: 1,
      }),
    });
  });
  await page.route("/api/v1/cookbook/dish-1", (route: Route) => {
    void route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        dishId: "dish-1",
        archivedAt: "2026-08-04T00:00:00Z",
        displayName: "番茄炖菜",
        internalName: "TomatoStew",
        categoryLabel: "主菜",
        description: "慢炖番茄与欧防风，暖胃又满足。",
        tags: ["stew"],
        gameplay: {
          ingredients: [
            {
              itemId: "24",
              displayName: "Parsnip",
              quantity: 1,
              mappingReason: "catalog match",
              catalogVersion: "stardew-1.6.15-v1",
            },
          ],
          recovery: {
            edibility: 80,
            energyRestore: 200,
            healthRestore: 90,
            calculationVersion: "stardew-1.6",
          },
          sellPrice: 220,
          isDrink: false,
          recipeUnlock: "DEFAULT",
        },
        visuals: {
          generatedArtAssetId: null,
          previewAssetId: null,
          iconSourceAssetId: null,
          icon16AssetId: "00000000-0000-4000-8000-000000000003",
          sourceRevision: 1,
          promptVersion: "visual-v1",
        },
      }),
    });
  });
  await page.route("/api/v1/exports/validate", (route: Route) => {
    void route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        valid: true,
        issues: [],
        validatedAt: "2026-08-04T00:00:00Z",
        validatorVersion: "task16-export-validator-v1",
      }),
    });
  });
  await page.route("/api/v1/exports", (route: Route) => {
    void route.fulfill({
      status: 201,
      contentType: "application/json",
      body: JSON.stringify(record),
    });
  });
  await page.route("/api/v1/exports/export-1", (route: Route) => {
    void route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(record),
    });
  });
  await page.route("**/api/v1/exports/export-1/download", (route: Route) => {
    const zip = buildZip({
      [`${PACK_ROOT}/manifest.json`]: Buffer.from(
        JSON.stringify({ Name: `Pelican Town Specials - ${PACK_SLUG}`, UniqueID: `D20260801.PelicanTownSpecials.${PACK_SLUG}` }),
      ),
      [`${PACK_ROOT}/content.json`]: Buffer.from(
        JSON.stringify({ Format: "2.9.0", Changes: [] }),
      ),
      [`${PACK_ROOT}/README.txt`]: Buffer.from("Pelican Town Specials - Content Pack\n"),
    });
    void route.fulfill({
      status: 200,
      contentType: "application/zip",
      headers: { "Content-Disposition": `attachment; filename="${ZIP_FILENAME}"` },
      body: zip,
    });
  });
  await page.route("/api/v1/exports/export-1/open-folder", (route: Route) => {
    void route.fulfill({ status: 204 });
  });
}

test.describe("export experience", () => {
  test("packs a menu, downloads the ZIP and verifies filename and structure", async ({
    page,
  }) => {
    await installApiRoutes(page);

    await page.goto("/cookbook");
    await expect(page.getByRole("button", { name: "打包菜单" })).toBeDisabled();
    await page.getByRole("checkbox").check();
    await expect(page.getByRole("button", { name: "打包菜单" })).toBeEnabled();
    await page.getByRole("button", { name: "打包菜单" }).click();
    await expect(page).toHaveURL(/\/pack-menu/);

    await expect(page.getByRole("heading", { name: "打包菜单" })).toBeVisible();
    await page.getByRole("button", { name: "校验" }).click();
    await expect(page.getByText("校验通过，可以打包。")).toBeVisible();
    await page.getByRole("button", { name: "打包菜单" }).click();
    await expect(page).toHaveURL(/\/bring-in-game\/export-1/);

    await expect(page.getByRole("heading", { name: "带进游戏" })).toBeVisible();
    await expect(page.getByRole("heading", { name: "家庭菜单" })).toBeVisible();
    await expect(page.getByText(/安装 SMAPI 与 Content Patcher/)).toBeVisible();

    const downloadPromise = page.waitForEvent("download");
    await page.getByRole("button", { name: "下载 Mod ZIP" }).click();
    const download = await downloadPromise;
    expect(download.suggestedFilename()).toBe(ZIP_FILENAME);

    const stream = await download.createReadStream();
    const chunks: Buffer[] = [];
    for await (const chunk of stream) {
      chunks.push(chunk as Buffer);
    }
    const zipBytes = Buffer.concat(chunks);
    expect(zipBytes.subarray(0, 4).toString("latin1")).toBe("PK");
    const latin = zipBytes.toString("latin1");
    expect(latin).toContain(`${PACK_ROOT}/manifest.json`);
    expect(latin).toContain(`${PACK_ROOT}/content.json`);
    expect(latin).toContain(`${PACK_ROOT}/README.txt`);
  });
});
