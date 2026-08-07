import { expect, test, type Page, type Route } from "@playwright/test";

/**
 * Fake-flow E2E for the generation experience. Every API call is intercepted
 * with page.route; no backend process and no model call is involved.
 */

const CSRF = "e2e-csrf-token";

type Draft = Record<string, unknown>;

type RouteState = {
  drafts: Record<string, Draft>;
  generateBody: string;
  onGenerate?: (draftId: string) => void;
  generationProgress?: Record<string, unknown>;
};

const source = { originalImageAssetId: "asset-1", contextText: null, language: "zh-CN" };

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
    createdAt: "2026-08-04T00:00:00Z",
    updatedAt: "2026-08-04T00:00:00Z",
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
    createdAt: "2026-08-04T00:00:00Z",
    updatedAt: "2026-08-04T00:00:00Z",
    archivedDishId: null,
    ...overrides,
  };
}

async function installApiRoutes(page: Page, state: RouteState): Promise<void> {
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
      body: JSON.stringify({ status: "ok", app: "PelicanTownSpecials", apiVersion: "v1" }),
    });
  });
  await page.route("/api/v1/cookbook", (route: Route) => {
    void route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ items: [], nextCursor: null, total: 0 }),
    });
  });
  await page.route("/api/v1/cookbook/*", (route: Route) => {
    void route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        dishId: "dish-1",
        displayName: "南瓜汤",
        status: "ARCHIVED",
        mode: "ASK_GUS",
        archivedAt: "2026-08-04T00:00:00Z",
        originalImageAssetId: "asset-1",
      }),
    });
  });

  await page.route("/api/v1/drafts/**", (route: Route) => {
    const url = new URL(route.request().url());
    const segments = url.pathname.split("/");
    const draftId = segments[4];
    const action = segments[5];
    const draft = state.drafts[draftId];
    if (!draft) {
      void route.fulfill({
        status: 404,
        contentType: "application/json",
        body: JSON.stringify({ error: { code: "PTS_DRAFT_NOT_FOUND", message: "草稿不存在" } }),
      });
      return;
    }
    if (route.request().method() === "GET") {
      if (action === "generation") {
        // Task 19.5: read-only progress snapshot. Default to idle unless the
        // test overrides state.generationProgress.
        const progress = state.generationProgress?.[draftId] ?? {
          draftId,
          active: false,
          attempt: null,
        };
        void route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(progress) });
        return;
      }
      void route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(draft) });
      return;
    }
    if (route.request().method() === "PATCH") {
      void route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(draft) });
      return;
    }
    if (route.request().method() === "POST") {
      if (action === "generate") {
        state.onGenerate?.(draftId);
        void route.fulfill({
          status: 200,
          contentType: "application/x-ndjson",
          body: state.generateBody,
        });
        return;
      }
      if (action === "cancel") {
        void route.fulfill({ status: 202 });
        return;
      }
      if (action === "archive") {
        void route.fulfill({
          status: 201,
          contentType: "application/json",
          body: JSON.stringify({
            dishId: "dish-1",
            displayName: "南瓜汤",
            status: "ARCHIVED",
            mode: "ASK_GUS",
            archivedAt: "2026-08-04T00:00:00Z",
            originalImageAssetId: "asset-1",
          }),
        });
        return;
      }
      if (action === "discard") {
        void route.fulfill({ status: 204 });
        return;
      }
      if (action === "convert-to-blueprint") {
        void route.fulfill({
          status: 201,
          contentType: "application/json",
          body: JSON.stringify(state.drafts["blueprint"]),
        });
        return;
      }
    }
    void route.fulfill({ status: 404 });
  });
}

test.describe("generation experience", () => {
  test("initial generation turns a DRAFT ask-gus into REVIEWABLE", async ({ page }) => {
    const drafts: Record<string, Draft> = {
      "ask-gus": askGusDraft({ status: "DRAFT", revision: 1, presentation: null, gameplay: null }),
    };
    const state: RouteState = {
      drafts,
      generateBody:
        '{"type":"attempt.started","attemptId":"a-1"}\n' +
        '{"type":"attempt.succeeded","attemptId":"a-1","draftRevision":3,"draft":{}}\n',
      onGenerate: (draftId) => {
        drafts[draftId] = askGusDraft({ status: "REVIEWABLE", revision: 3 });
      },
    };
    await installApiRoutes(page, state);

    await page.goto("/drafts/ask-gus");
    await expect(page.getByRole("button", { name: "开始生成" })).toBeVisible();
    await page.getByRole("button", { name: "开始生成" }).click();

    await expect(page.getByRole("button", { name: "完整重新生成" })).toBeVisible();
    await expect(page.getByRole("heading", { name: "南瓜汤" })).toBeVisible();
  });

  test("failed full regeneration restores the old result", async ({ page }) => {
    const state: RouteState = {
      drafts: { "ask-gus": askGusDraft() },
      generateBody:
        JSON.stringify({
          type: "attempt.failed",
          attemptId: "a-1",
          error: {
            code: "PTS_GEN_VALIDATION_FAILED",
            message: "生成结果未通过校验。",
            retryable: false,
            requestId: "req-1",
            recommendedAction: "",
          },
        }) + "\n",
    };
    await installApiRoutes(page, state);

    await page.goto("/drafts/ask-gus");
    await expect(page.getByRole("button", { name: "完整重新生成" })).toBeVisible();
    await page.getByRole("button", { name: "完整重新生成" }).click();

    await expect(page.getByText("生成结果未通过校验。")).toBeVisible();
    await expect(page.getByRole("heading", { name: "南瓜汤" })).toBeVisible();
    await expect(page.getByRole("button", { name: "重试生成" })).toBeVisible();
  });

  test("cancelling a full regeneration keeps the page recoverable", async ({ page }) => {
    const state: RouteState = {
      drafts: { "ask-gus": askGusDraft() },
      generateBody: '{"type":"attempt.started","attemptId":"a-1"}\n',
    };
    await installApiRoutes(page, state);

    await page.goto("/drafts/ask-gus");
    await expect(page.getByRole("button", { name: "完整重新生成" })).toBeVisible();
    await page.getByRole("button", { name: "完整重新生成" }).click();

    await expect(page.getByRole("button", { name: "取消生成" })).toBeVisible();
    await page.getByRole("button", { name: "取消生成" }).click();

    await expect(page.getByText("已取消生成。")).toBeVisible();
    await expect(page.getByRole("button", { name: "完整重新生成" })).toBeVisible();
  });

  test("successful full regeneration replaces the result", async ({ page }) => {
    const drafts: Record<string, Draft> = { "ask-gus": askGusDraft() };
    const state: RouteState = {
      drafts,
      generateBody:
        '{"type":"attempt.started","attemptId":"a-1"}\n' +
        '{"type":"stage.started","stage":"DISH_ANALYSIS","ordinal":2,"total":9}\n' +
        '{"type":"attempt.succeeded","attemptId":"a-1","draftRevision":4,"draft":{}}\n',
      onGenerate: (draftId) => {
        drafts[draftId] = askGusDraft({
          revision: 4,
          presentation: { ...askGusDraft().presentation, displayName: "南瓜奶油汤" },
        });
      },
    };
    await installApiRoutes(page, state);

    await page.goto("/drafts/ask-gus");
    await expect(page.getByRole("button", { name: "完整重新生成" })).toBeVisible();
    await page.getByRole("button", { name: "完整重新生成" }).click();

    await expect(page.getByText("南瓜奶油汤")).toBeVisible();
    await expect(page.getByText(/版本：4/)).toBeVisible();
  });

  test("accepting archives the dish and navigates to the cookbook", async ({ page }) => {
    const state: RouteState = {
      drafts: { "ask-gus": askGusDraft() },
      generateBody: "",
    };
    await installApiRoutes(page, state);

    await page.goto("/drafts/ask-gus");
    await expect(page.getByRole("button", { name: "接受并加入收集品" })).toBeVisible();
    await page.getByRole("button", { name: "接受并加入收集品" }).click();

    await expect(page).toHaveURL(/\/cookbook\/dish-1/);
  });

  test("review page offers no convert-to-blueprint entry", async ({ page }) => {
    const state: RouteState = {
      drafts: { "ask-gus": askGusDraft() },
      generateBody: "",
    };
    await installApiRoutes(page, state);

    await page.goto("/drafts/ask-gus");
    await expect(page.getByRole("button", { name: "完整重新生成" })).toBeVisible();
    // F19-3-001: the convert-to-blueprint entry was removed; the page stays on
    // the ask-gus review route (blueprint create flow lives in the homepage).
    await expect(page.getByRole("button", { name: "进入料理蓝图" })).toHaveCount(0);
    await expect(page.getByRole("heading", { name: "编辑料理蓝图" })).toHaveCount(0);
  });

  test("refresh rehydrates the running generation stage", async ({ page }) => {
    // A draft the server is currently generating (GENERATING) with a progress
    // snapshot must re-show its stage after a reload instead of a blank
    // "start generation" state (Task 19.5, R5.1-1).
    const drafts: Record<string, Draft> = {
      "ask-gus": askGusDraft({ status: "GENERATING", revision: 1, presentation: null, gameplay: null }),
    };
    const state: RouteState = {
      drafts,
      generateBody: "",
      generationProgress: {
        "ask-gus": {
          draftId: "ask-gus",
          active: true,
          attempt: {
            attemptId: "a-1",
            draftId: "ask-gus",
            kind: "INITIAL",
            sourceRevision: 1,
            status: "RUNNING",
            currentStage: "DISH_ANALYSIS",
            stages: [
              { stage: "INPUT_VALIDATION", status: "SUCCEEDED", retryCount: 0, startedAt: "2026-08-04T00:00:00Z", finishedAt: "2026-08-04T00:00:00Z", error: null },
              { stage: "DISH_ANALYSIS", status: "RUNNING", retryCount: 0, startedAt: "2026-08-04T00:00:00Z", finishedAt: null, error: null },
            ],
            startedAt: "2026-08-04T00:00:00Z",
            finishedAt: null,
            error: null,
          },
        },
      },
    };
    await installApiRoutes(page, state);

    await page.goto("/drafts/ask-gus");
    // The hydrated progress shows the current stage, not a "start" button.
    await expect(page.getByRole("button", { name: "开始生成" })).toHaveCount(0);
    await expect(page.getByText("菜品分析")).toBeVisible();
    await expect(page.getByRole("button", { name: "取消生成" })).toBeVisible();
  });

  test("blueprint update preview returns to REVIEWABLE", async ({ page }) => {
    const drafts: Record<string, Draft> = {
      blueprint: blueprintDraft({ status: "STALE_PREVIEW", revision: 2 }),
    };
    const state: RouteState = {
      drafts,
      generateBody:
        '{"type":"attempt.started","attemptId":"a-1"}\n' +
        '{"type":"attempt.succeeded","attemptId":"a-1","draftRevision":3,"draft":{}}\n',
      onGenerate: (draftId) => {
        drafts[draftId] = blueprintDraft({ status: "REVIEWABLE", revision: 3 });
      },
    };
    await installApiRoutes(page, state);

    await page.goto("/drafts/blueprint");
    await expect(page.getByRole("button", { name: "更新预览" })).toBeVisible();
    await page.getByRole("button", { name: "更新预览" }).click();

    await expect(page.getByRole("button", { name: "接受并加入收集品" })).toBeVisible();
  });
});
