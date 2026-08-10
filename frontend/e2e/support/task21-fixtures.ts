import { resolve } from "node:path";
import { fileURLToPath } from "node:url";
import type { Page } from "@playwright/test";

const FIXTURE_ICON_ROOT = fileURLToPath(new URL("../../public/assets/game/fixtures", import.meta.url));
const FIXTURE_PREVIEW = fileURLToPath(new URL("../../public/assets/ui/banner.jpg", import.meta.url));

export const task21Dishes = [
  {
    dishId: "dish-1",
    archivedAt: "2026-08-08T00:00:00Z",
    displayName: "番茄酱汁煎鲑鱼",
    categoryLabel: "主菜",
    description: "西式经典料理，带着酸甜的番茄香气。",
    tags: ["鲜美", "酸甜"],
  },
  {
    dishId: "dish-2",
    archivedAt: "2026-08-07T00:00:00Z",
    displayName: "菠菜烟熏三文鱼",
    categoryLabel: "主菜",
    description: "烟熏与青草香气的组合。",
    tags: ["烟熏"],
  },
  {
    dishId: "dish-3",
    archivedAt: "2026-08-06T00:00:00Z",
    displayName: "春日面碗",
    categoryLabel: "汤类",
    description: "一碗春天气息的热汤面。",
    tags: ["春日"],
  },
  {
    dishId: "dish-4",
    archivedAt: "2026-08-05T00:00:00Z",
    displayName: "蓝色夏日饮品",
    categoryLabel: "饮品",
    description: "适合夏日的清凉饮品。",
    tags: ["夏日"],
  },
  {
    dishId: "dish-5",
    archivedAt: "2026-08-04T00:00:00Z",
    displayName: "木桶烤蔬菜",
    categoryLabel: "配菜",
    description: "农场收获季的烤蔬菜。",
    tags: ["家常"],
  },
];

const gameplay = {
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
};

function cookbookVisuals(dishId: string) {
  return {
    generatedArtAssetId: null,
    previewAssetId: `fixture-preview-${dishId}`,
    iconSourceAssetId: null,
    icon16AssetId: `fixture-icon-${dishId}`,
    sourceRevision: 1,
    promptVersion: "fixture-v1",
  };
}

export function task21Draft(mode: "ASK_GUS" | "BLUEPRINT", status: string) {
  return {
    draftId: mode === "ASK_GUS" ? "ask-gus" : "blueprint",
    mode,
    baseTemplateVersion: mode === "BLUEPRINT" ? "blueprint-v1" : null,
    status,
    revision: mode === "BLUEPRINT" ? 2 : 3,
    source: { originalImageAssetId: "asset-1", contextText: null, language: "zh-CN" },
    presentation: {
      displayName: mode === "ASK_GUS" ? "南瓜汤" : "南瓜浓汤",
      internalName: mode === "ASK_GUS" ? "PumpkinSoup" : "PumpkinSoup2",
      categoryLabel: "汤类",
      description: "香甜的南瓜汤。",
      gusComment: "这道菜很有鹈鹕镇的味道。",
      tags: ["秋日"],
    },
    gameplay,
    visuals:
      mode === "ASK_GUS" && status === "REVIEWABLE"
        ? cookbookVisuals("dish-3")
        : null,
    provenance: {
      mode,
      authorityByField: {},
      visionModel: mode === "ASK_GUS" ? "fixture-vision" : null,
      textModel: null,
      imageModel: null,
      promptVersions: {},
      generationSource: mode === "ASK_GUS" ? "FRESH_GENERATION" : "USER_AUTHORED",
      canonicalDishSignature: null,
      cacheEligibility: mode === "ASK_GUS",
    },
    lastError: null,
    createdAt: "2026-08-08T00:00:00Z",
    updatedAt: "2026-08-08T00:00:00Z",
    archivedDishId: null,
  };
}

export async function installTask21Routes(page: Page): Promise<void> {
  await page.route("**/session/status", (route) =>
    route.fulfill({ status: 200, headers: { "X-PTS-CSRF": "task21-csrf" }, body: "" }),
  );
  await page.route("**/api/v1/health", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ status: "ok", app: "PelicanTownSpecials", apiVersion: "v1" }),
    }),
  );
  await page.route("**/app/heartbeat", (route) => route.fulfill({ status: 204 }));
  await page.route("**/api/v1/settings/provider", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        providerKind: "OPENAI_COMPATIBLE",
        baseUrl: "https://fixture.invalid/v1",
        visionModel: "fixture-vision",
        textModel: "fixture-text",
        imageModel: "fixture-image",
        chatTimeoutSeconds: 120,
        imageTimeoutSeconds: 300,
        maxAutomaticRetries: 2,
        apiKeyConfigured: true,
        apiKeySource: "ENVIRONMENT",
      }),
    }),
  );
  await page.route("**/api/v1/drafts", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        items: [
          {
            draftId: "running",
            mode: "ASK_GUS",
            status: "GENERATING",
            revision: 1,
            updatedAt: "2026-08-08T00:00:00Z",
            displayName: "番茄酱汁煎鲑鱼",
            originalImageAssetId: "asset-1",
          },
          {
            draftId: "stale",
            mode: "BLUEPRINT",
            status: "STALE_PREVIEW",
            revision: 2,
            updatedAt: "2026-08-07T00:00:00Z",
            displayName: "菠菜烟熏三文鱼",
            originalImageAssetId: "asset-2",
          },
          {
            draftId: "reviewable",
            mode: "ASK_GUS",
            status: "REVIEWABLE",
            revision: 3,
            updatedAt: "2026-08-06T00:00:00Z",
            displayName: "春日面碗",
            originalImageAssetId: "asset-3",
          },
        ],
        nextCursor: null,
        total: 3,
      }),
    }),
  );
  await page.route("**/api/v1/drafts/*/generation", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ draftId: "running", active: true, attempt: null }),
    }),
  );
  await page.route("**/api/v1/drafts/ask-gus", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(task21Draft("ASK_GUS", "REVIEWABLE")),
    }),
  );
  await page.route("**/api/v1/drafts/blueprint", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(task21Draft("BLUEPRINT", "STALE_PREVIEW")),
    }),
  );
  await page.route("**/api/v1/cookbook", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ items: task21Dishes, nextCursor: null, total: task21Dishes.length }),
    }),
  );
  await page.route("**/api/v1/cookbook/dish-1", (route) => {
    const dish = task21Dishes[0];
    return route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        ...dish,
        internalName: "FixtureDish",
        gameplay,
        visuals: cookbookVisuals(dish.dishId),
      }),
    });
  });
  await page.route("**/api/v1/cookbook/*", (route) => {
    const dishId = new URL(route.request().url()).pathname.split("/").pop();
    const dish = task21Dishes.find((item) => item.dishId === dishId) ?? task21Dishes[0];
    return route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        ...dish,
        internalName: "FixtureDish",
        gameplay,
        visuals: cookbookVisuals(dish.dishId),
      }),
    });
  });
  const exportRecord = {
    exportId: "export-1",
    spec: {
      dishIds: ["dish-1", "dish-2", "dish-3"],
      packDisplayName: "家庭菜单",
      packSlug: "FamilyMenu",
      version: "1.0.0",
      description: "一份装满鹈鹕镇风味的菜单。",
      language: "zh-CN",
    },
    authorName: "D20260808",
    uniqueId: "D20260808.PelicanTownSpecials.FamilyMenu",
    status: "SUCCEEDED",
    dishContentHashes: {},
    compilerVersion: "task16-export-compiler-v1",
    gameVersion: "1.6.15",
    contentPatcherFormat: "2.9.0",
    validation: {
      valid: true,
      issues: [],
      validatedAt: "2026-08-08T00:00:00Z",
      validatorVersion: "task21-fixture-v1",
    },
    artifactAssetId: null,
    createdAt: "2026-08-08T00:00:00Z",
    finishedAt: "2026-08-08T00:00:01Z",
    error: null,
  };
  await page.route("**/api/v1/exports/export-1", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(exportRecord),
    }),
  );
  await page.route("**/api/v1/exports/validate", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(exportRecord.validation),
    }),
  );
  await page.route("**/api/v1/assets/*", (route) => route.fulfill({ status: 404 }));
  await page.route("**/api/v1/assets/fixture-preview-*", (route) =>
    route.fulfill({ path: FIXTURE_PREVIEW }),
  );
  await page.route("**/api/v1/assets/fixture-icon-*", (route) => {
    const assetId = new URL(route.request().url()).pathname.split("/").pop() ?? "";
    const dishId = assetId.replace("fixture-icon-", "");
    return route.fulfill({ path: resolve(FIXTURE_ICON_ROOT, `${dishId}.png`) });
  });
}
