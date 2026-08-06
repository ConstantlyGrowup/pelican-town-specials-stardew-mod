import { expect, test, type Page, type Route } from "@playwright/test";

/**
 * Fake-flow full-journey E2E (Task 19 Step 6).
 *
 * Covers: 设置 → 上传 → Ask Gus → 完整重生成 → 接受 → Cookbook → 第二个
 * Blueprint → 接受 → 多选 → Pack the Menu → 下载 ZIP → Bring It In-Game.
 *
 * Every API call is intercepted with page.route; no backend process and no
 * model call is involved. Asserts:
 *   - Ask Gus offers only full regeneration (no partial redo controls).
 *   - Cookbook never reveals a dish's source mode (ASK_GUS / BLUEPRINT).
 */

const CSRF = "e2e-csrf-token";
const PACK_SLUG = "FamilyMenu";
const ZIP_FILENAME = `[CP] Pelican Town Specials - ${PACK_SLUG}.zip`;
const PACK_ROOT = `[CP] Pelican Town Specials - ${PACK_SLUG}`;

type Draft = Record<string, unknown>;
type Dish = Record<string, unknown>;
type ExportRecord = Record<string, unknown>;

const source = { originalImageAssetId: "asset-1", contextText: null, language: "zh-CN" };

const PNG_BYTES = Buffer.from(
  "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg==",
  "base64",
);

function askGusDraft(overrides: Record<string, unknown> = {}): Draft {
  return {
    draftId: "ask-gus",
    mode: "ASK_GUS",
    baseTemplateVersion: null,
    status: "REVIEWABLE",
    revision: 3,
    source,
    presentation: {
      displayName: "南瓜汤",
      internalName: "PumpkinSoup",
      categoryLabel: "汤类",
      description: "香甜的南瓜汤。",
      gusComment: null,
      tags: ["fall"],
    },
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
        edibility: 20,
        energyRestore: 50,
        healthRestore: 22,
        calculationVersion: "stardew-1.6",
      },
      sellPrice: 35,
      isDrink: false,
      recipeUnlock: "DEFAULT",
      buff: null,
    },
    visuals: null,
    provenance: {
      mode: "ASK_GUS",
      authorityByField: {},
      visionModel: "vision-model",
      textModel: null,
      imageModel: null,
      promptVersions: {},
      generationSource: "FRESH_GENERATION",
      canonicalDishSignature: null,
      cacheEligibility: true,
    },
    lastError: null,
    createdAt: "2026-08-06T00:00:00Z",
    updatedAt: "2026-08-06T00:00:00Z",
    archivedDishId: null,
    ...overrides,
  };
}

function blueprintDraft(overrides: Record<string, unknown> = {}): Draft {
  return {
    draftId: "blueprint",
    mode: "BLUEPRINT",
    baseTemplateVersion: "blueprint-v1",
    status: "STALE_PREVIEW",
    revision: 2,
    source,
    presentation: {
      displayName: "南瓜浓汤",
      internalName: "PumpkinSoup2",
      categoryLabel: "汤类",
      description: "更浓郁的南瓜汤。",
      gusComment: null,
      tags: ["fall"],
    },
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
        edibility: 25,
        energyRestore: 60,
        healthRestore: 27,
        calculationVersion: "stardew-1.6",
      },
      sellPrice: 40,
      isDrink: false,
      recipeUnlock: "DEFAULT",
      buff: null,
    },
    visuals: null,
    provenance: {
      mode: "BLUEPRINT",
      authorityByField: {},
      visionModel: null,
      textModel: null,
      imageModel: null,
      promptVersions: {},
      generationSource: "USER_AUTHORED",
      canonicalDishSignature: null,
      cacheEligibility: false,
    },
    lastError: null,
    createdAt: "2026-08-06T00:00:00Z",
    updatedAt: "2026-08-06T00:00:00Z",
    archivedDishId: null,
    ...overrides,
  };
}

function dishView(overrides: Record<string, unknown> = {}): Dish {
  return {
    dishId: "dish-1",
    displayName: "南瓜汤",
    internalName: "PumpkinSoup",
    categoryLabel: "汤类",
    description: "香甜的南瓜汤。",
    tags: ["fall"],
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
        edibility: 20,
        energyRestore: 50,
        healthRestore: 22,
        calculationVersion: "stardew-1.6",
      },
      sellPrice: 35,
      isDrink: false,
      recipeUnlock: "DEFAULT",
    },
    visuals: {
      generatedArtAssetId: null,
      previewAssetId: null,
      iconSourceAssetId: null,
      icon16AssetId: null,
      sourceRevision: 1,
      promptVersion: "visual-v1",
    },
    ...overrides,
  };
}

const exportRecord: ExportRecord = {
  exportId: "export-1",
  spec: {
    dishIds: ["dish-1", "dish-2"],
    packDisplayName: "家庭菜单",
    packSlug: PACK_SLUG,
    version: "1.0.0",
    description: "一份装满鹈鹕镇风味的菜单。",
    language: "zh-CN",
  },
  authorName: "D20260806",
  uniqueId: `D20260806.PelicanTownSpecials.${PACK_SLUG}`,
  status: "SUCCEEDED",
  dishContentHashes: { "dish-1": "a".repeat(64), "dish-2": "b".repeat(64) },
  compilerVersion: "task16-export-compiler-v1",
  gameVersion: "1.6.15",
  contentPatcherFormat: "2.9.0",
  validation: {
    valid: true,
    issues: [],
    validatedAt: "2026-08-06T00:00:00Z",
    validatorVersion: "task16-export-validator-v1",
  },
  artifactAssetId: "00000000-0000-4000-8000-000000000004",
  createdAt: "2026-08-06T00:00:00Z",
  finishedAt: "2026-08-06T00:00:01Z",
  error: null,
};

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

type JourneyState = {
  drafts: Record<string, Draft>;
  dishes: Record<string, Dish>;
  generateCount: Record<string, number>;
  assetSeq: number;
};

function nextAskGusDraft(current: Draft | undefined, count: number): Draft {
  const revision = (current?.revision as number | undefined) ?? 1;
  if (count <= 1) {
    return askGusDraft({
      status: "REVIEWABLE",
      revision: Math.max(2, revision),
      presentation: askGusDraft().presentation,
    });
  }
  return askGusDraft({
    status: "REVIEWABLE",
    revision: revision + 1,
    presentation: {
      ...(askGusDraft().presentation as Record<string, unknown>),
      displayName: "南瓜奶油汤",
    },
  });
}

function nextBlueprintDraft(current: Draft | undefined): Draft {
  const revision = (current?.revision as number | undefined) ?? 2;
  return blueprintDraft({
    status: "REVIEWABLE",
    revision: Math.max(3, revision),
  });
}

async function installApiRoutes(page: Page, state: JourneyState): Promise<void> {
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
      body: JSON.stringify(settingsView),
    });
  });
  await page.route("/api/v1/settings/provider/key", (route: Route) => {
    void route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ apiKeyConfigured: true, apiKeySource: "ENVIRONMENT" }),
    });
  });

  await page.route("/api/v1/assets/images", (route: Route) => {
    state.assetSeq += 1;
    void route.fulfill({
      status: 201,
      contentType: "application/json",
      body: JSON.stringify({
        assetId: `asset-${state.assetSeq}`,
        kind: "ORIGINAL_IMAGE",
        mediaType: "image/png",
        sha256: "a".repeat(64),
        byteSize: 1234,
        createdAt: "2026-08-06T00:00:00Z",
        width: 8,
        height: 8,
        sourceRevision: 1,
        attemptId: null,
      }),
    });
  });

  await page.route("/api/v1/drafts", (route: Route) => {
    if (route.request().method() !== "POST") {
      void route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ items: [], nextCursor: null, total: 0 }) });
      return;
    }
    const body = route.request().postDataJSON() as {
      mode?: string;
      source?: { originalImageAssetId?: string };
    };
    const isBlueprint = body.mode === "BLUEPRINT";
    const draftId = isBlueprint ? "blueprint" : "ask-gus";
    const assetId = body.source?.originalImageAssetId ?? "asset-1";
    const draft = isBlueprint
      ? blueprintDraft({ source: { ...source, originalImageAssetId: assetId } })
      : askGusDraft({
          status: "DRAFT",
          revision: 1,
          presentation: null,
          gameplay: null,
          source: { ...source, originalImageAssetId: assetId },
        });
    state.drafts[draftId] = draft;
    void route.fulfill({
      status: 201,
      contentType: "application/json",
      body: JSON.stringify(draft),
    });
  });

  await page.route("/api/v1/drafts/**", (route: Route) => {
    const url = new URL(route.request().url());
    const segments = url.pathname.split("/");
    const draftId = segments[4];
    const action = segments[5];
    const method = route.request().method();

    if (method === "GET") {
      const draft = state.drafts[draftId];
      if (!draft) {
        void route.fulfill({ status: 404, contentType: "application/json", body: JSON.stringify({ error: { code: "PTS_DRAFT_NOT_FOUND", message: "草稿不存在" } }) });
        return;
      }
      void route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(draft) });
      return;
    }

    if (method === "PATCH") {
      const draft = state.drafts[draftId];
      void route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(draft) });
      return;
    }

    if (method === "POST") {
      if (action === "generate") {
        const count = (state.generateCount[draftId] ?? 0) + 1;
        state.generateCount[draftId] = count;
        const current = state.drafts[draftId];
        const updated =
          draftId === "ask-gus"
            ? nextAskGusDraft(current, count)
            : nextBlueprintDraft(current);
        state.drafts[draftId] = updated;
        const revision = updated.revision as number;
        void route.fulfill({
          status: 200,
          contentType: "application/x-ndjson",
          body:
            '{"type":"attempt.started","attemptId":"a-1"}\n' +
            '{"type":"stage.started","stage":"DISH_ANALYSIS","ordinal":2,"total":9}\n' +
            `{"type":"attempt.succeeded","attemptId":"a-1","draftRevision":${revision},"draft":{}}\n`,
        });
        return;
      }
      if (action === "cancel") {
        void route.fulfill({ status: 202 });
        return;
      }
      if (action === "archive") {
        const dishId = draftId === "ask-gus" ? "dish-1" : "dish-2";
        const dish = dishView(
          draftId === "ask-gus"
            ? { dishId, displayName: "南瓜汤", internalName: "PumpkinSoup" }
            : { dishId, displayName: "南瓜浓汤", internalName: "PumpkinSoup2" },
        );
        state.dishes[dishId] = dish;
        void route.fulfill({
          status: 201,
          contentType: "application/json",
          body: JSON.stringify(dish),
        });
        return;
      }
      if (action === "convert-to-blueprint") {
        const blueprint = blueprintDraft();
        state.drafts["blueprint"] = blueprint;
        void route.fulfill({
          status: 201,
          contentType: "application/json",
          body: JSON.stringify(blueprint),
        });
        return;
      }
      if (action === "discard") {
        void route.fulfill({ status: 204 });
        return;
      }
    }
    void route.fulfill({ status: 404 });
  });

  await page.route("/api/v1/cookbook", (route: Route) => {
    const items = Object.values(state.dishes);
    void route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ items, nextCursor: null, total: items.length }),
    });
  });

  await page.route("/api/v1/cookbook/*", (route: Route) => {
    const dishId = route.request().url().split("/").pop() ?? "";
    const dish = state.dishes[dishId];
    if (!dish) {
      void route.fulfill({ status: 404 });
      return;
    }
    void route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(dish) });
  });

  await page.route("/api/v1/exports/validate", (route: Route) => {
    void route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        valid: true,
        issues: [],
        validatedAt: "2026-08-06T00:00:00Z",
        validatorVersion: "task16-export-validator-v1",
      }),
    });
  });

  await page.route("/api/v1/exports", (route: Route) => {
    void route.fulfill({
      status: 201,
      contentType: "application/json",
      body: JSON.stringify(exportRecord),
    });
  });

  await page.route("/api/v1/exports/export-1", (route: Route) => {
    void route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(exportRecord),
    });
  });

  await page.route("**/api/v1/exports/export-1/download", (route: Route) => {
    const zip = buildZip({
      [`${PACK_ROOT}/manifest.json`]: Buffer.from(
        JSON.stringify({ Name: `Pelican Town Specials - ${PACK_SLUG}`, UniqueID: `D20260806.PelicanTownSpecials.${PACK_SLUG}` }),
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

test.describe("full journey", () => {
  test("settings, two dishes, pack the menu and download the ZIP", async ({ page }) => {
    const state: JourneyState = {
      drafts: {},
      dishes: {},
      generateCount: {},
      assetSeq: 0,
    };
    await installApiRoutes(page, state);

    // 1. Settings: save a provider key.
    await page.goto("/settings");
    await expect(page.getByRole("heading", { name: "Provider 设置" })).toBeVisible();
    await expect(page.getByText("未配置")).toBeVisible();
    await page.locator("#apiKey").fill("sk-e2e-key");
    await page.getByRole("button", { name: "保存 Key" }).click();
    await expect(page.getByText("已配置")).toBeVisible();

    // 2. Upload a photo and create an Ask Gus draft.
    await page.goto("/create");
    await expect(page.getByRole("heading", { name: "创建一道菜" })).toBeVisible();
    await page.setInputFiles("#dishPhoto", {
      name: "photo.png",
      mimeType: "image/png",
      buffer: PNG_BYTES,
    });
    await expect(page.getByText("图片已就绪，可以创建草稿。")).toBeVisible();
    await page.getByRole("button", { name: "创建草稿" }).click();
    await expect(page).toHaveURL(/\/drafts\/ask-gus/);

    // 3. Initial Ask Gus generation.
    await expect(page.getByRole("button", { name: "开始生成" })).toBeVisible();
    await page.getByRole("button", { name: "开始生成" }).click();
    await expect(page.getByRole("heading", { name: "南瓜汤" })).toBeVisible();
    await expect(page.getByRole("button", { name: "接受并加入收集品" })).toBeVisible();

    // Ask Gus must offer only full regeneration: no partial redo controls.
    await expect(page.getByRole("button", { name: "完整重新生成" })).toBeVisible();
    await expect(page.getByRole("button", { name: "保存修改" })).toHaveCount(0);
    await expect(page.getByRole("button", { name: "更新预览" })).toHaveCount(0);

    // 4. Full regeneration replaces the result.
    await page.getByRole("button", { name: "完整重新生成" }).click();
    await expect(page.getByRole("heading", { name: "南瓜奶油汤" })).toBeVisible();
    await expect(page.getByText(/版本：3/)).toBeVisible();

    // 5. Accept into the cookbook.
    await page.getByRole("button", { name: "接受并加入收集品" }).click();
    await expect(page).toHaveURL(/\/cookbook\/dish-1/);
    await expect(page.getByRole("heading", { name: "南瓜汤" })).toBeVisible();

    // 6. Cookbook must never expose the dish's source mode.
    await expect(page.getByText("问问 Gus")).toHaveCount(0);
    await expect(page.getByText("料理蓝图")).toHaveCount(0);

    // 7. Second dish through the Blueprint editor.
    await page.goto("/create");
    await page.getByRole("button", { name: "料理蓝图" }).click();
    await page.setInputFiles("#dishPhoto", {
      name: "photo2.png",
      mimeType: "image/png",
      buffer: PNG_BYTES,
    });
    await expect(page.getByText("图片已就绪，可以创建草稿。")).toBeVisible();
    await page.getByRole("button", { name: "创建草稿" }).click();
    await expect(page).toHaveURL(/\/drafts\/blueprint/);
    await expect(page.getByRole("heading", { name: "编辑料理蓝图" })).toBeVisible();
    await expect(page.getByRole("button", { name: "更新预览" })).toBeVisible();
    await page.getByRole("button", { name: "更新预览" }).click();
    await expect(page.getByRole("button", { name: "接受并加入收集品" })).toBeVisible();
    await page.getByRole("button", { name: "接受并加入收集品" }).click();
    await expect(page).toHaveURL(/\/cookbook\/dish-2/);

    // 8. Multi-select both dishes and pack the menu.
    await page.goto("/cookbook");
    await expect(page.getByRole("heading", { name: "收集品" })).toBeVisible();
    const checkboxes = page.getByRole("checkbox");
    await expect(checkboxes).toHaveCount(2);
    await checkboxes.nth(0).check();
    await checkboxes.nth(1).check();
    const packButton = page.getByRole("button", { name: "打包菜单" });
    await expect(packButton).toBeEnabled();
    await packButton.click();
    await expect(page).toHaveURL(/\/pack-menu/);

    // 9. Validate and pack the menu.
    await expect(page.getByRole("heading", { name: "打包菜单" })).toBeVisible();
    await page.getByRole("button", { name: "校验" }).click();
    await expect(page.getByText("校验通过，可以打包。")).toBeVisible();
    await page.getByRole("button", { name: "打包菜单" }).click();
    await expect(page).toHaveURL(/\/bring-in-game\/export-1/);

    // 10. Bring It In-Game and download the ZIP.
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
  });
});
