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
  /** Optional per-draft NDJSON generate bodies; falls back to generateBody. */
  generateBodyFor?: Record<string, string>;
  /** When present, the next generate call for that draft is rejected with a
   * 409 PTS_GEN_BUSY envelope (details.activeCount/maxConcurrent); the entry
   * is consumed so a later retry streams normally. Enables the busy-hint-then-
   * retry flow without a backend. */
  generateBusyOnceFor?: Record<string, unknown>;
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
        if (state.generateBusyOnceFor && draftId in state.generateBusyOnceFor) {
          // M8 Task 29: the 4th concurrent request is rejected up front with
          // PTS_GEN_BUSY (activeCount/maxConcurrent) before any stream starts.
          // The busy rejection must NOT touch onGenerate: the mock draft keeps
          // its exact server-side state (M8-D02: no draft change, no attempt).
          delete state.generateBusyOnceFor[draftId];
          void route.fulfill({
            status: 409,
            contentType: "application/json",
            body: JSON.stringify({
              error: {
                code: "PTS_GEN_BUSY",
                message: "当前已有一个生成任务在运行，请稍后重试。",
                retryable: false,
                requestId: "req-busy",
                recommendedAction: "",
                details: { activeCount: 3, maxConcurrent: 3, draftId },
              },
            }),
          });
          return;
        }
        state.onGenerate?.(draftId);
        void route.fulfill({
          status: 200,
          contentType: "application/x-ndjson",
          body: state.generateBodyFor?.[draftId] ?? state.generateBody,
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
    await expect(page.getByText("识别菜品")).toBeVisible();
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

  test("busy rejection shows the bilingual limit hint and a retry succeeds once a slot frees", async ({ page }) => {
    const drafts: Record<string, Draft> = {
      "ask-gus": askGusDraft({ status: "DRAFT", revision: 1, presentation: null, gameplay: null }),
    };
    const state: RouteState = {
      drafts,
      generateBody:
        '{"type":"attempt.started","attemptId":"a-1"}\n' +
        '{"type":"attempt.succeeded","attemptId":"a-1","draftRevision":3,"draft":{}}\n',
      generateBusyOnceFor: { "ask-gus": {} },
      onGenerate: (draftId) => {
        drafts[draftId] = askGusDraft({ status: "REVIEWABLE", revision: 3 });
      },
    };
    await installApiRoutes(page, state);

    await page.goto("/drafts/ask-gus");
    await expect(page.getByRole("button", { name: "开始生成" })).toBeVisible();
    const draftBeforeRejection = state.drafts["ask-gus"];
    await page.getByRole("button", { name: "开始生成" }).click();

    // The 4th draft (busy) shows the localized zh limit hint instead of the
    // backend message, and the draft keeps its original state.
    await expect(page.getByText("最多同时运行 3 个生成任务，请等待其中一个完成后重试。")).toBeVisible();
    await expect(page.getByText("当前已有一个生成任务在运行，请稍后重试。")).toHaveCount(0);
    await expect(page.getByRole("button", { name: "开始生成" })).toBeVisible();
    await expect(page.getByRole("button", { name: "重试生成" })).toBeVisible();
    // M8-D02: the busy rejection never touches the draft server-side — the
    // mock draft is the same object, still DRAFT (onGenerate was not called).
    expect(state.drafts["ask-gus"]).toBe(draftBeforeRejection);
    expect(state.drafts["ask-gus"].status).toBe("DRAFT");

    // A slot frees: retrying streams immediately to success (the 200 path
    // does advance the draft through onGenerate).
    await page.getByRole("button", { name: "重试生成" }).click();
    await expect(page.getByRole("button", { name: "完整重新生成" })).toBeVisible();
    await expect(page.getByRole("heading", { name: "南瓜汤" })).toBeVisible();
    expect(state.drafts["ask-gus"].status).toBe("REVIEWABLE");

    // en-US: the same busy rejection shows the English limit hint and again
    // leaves the draft state untouched.
    await page.addInitScript((locale: string) => {
      window.localStorage.setItem("pts-locale", locale);
    }, "en-US");
    state.generateBusyOnceFor = { "ask-gus": {} };
    await page.reload();
    await expect(page.getByRole("button", { name: "Full regenerate" })).toBeVisible();
    const enDraftBeforeRejection = state.drafts["ask-gus"];
    await page.getByRole("button", { name: "Full regenerate" }).click();
    await expect(page.getByText("Up to 3 generations can run at the same time. Please wait for one to finish before retrying.")).toBeVisible();
    expect(state.drafts["ask-gus"]).toBe(enDraftBeforeRejection);
    expect(state.drafts["ask-gus"].status).toBe("REVIEWABLE");
  });

  test("three drafts generate in parallel without cross-page state bleed", async ({ context }) => {
    const stageByDraft: Record<string, string> = {
      "draft-a": "DISH_ANALYSIS",
      "draft-b": "INGREDIENT_MAPPING",
      "draft-c": "GAMEPLAY_DESIGN",
    };
    const drafts: Record<string, Draft> = {};
    const generateBodyFor: Record<string, string> = {};
    for (const draftId of ["draft-a", "draft-b", "draft-c"]) {
      drafts[draftId] = askGusDraft({
        draftId,
        status: "DRAFT",
        revision: 1,
        presentation: null,
        gameplay: null,
      });
      // Per-draft stage streams (never terminated): each page must observe
      // only its own stage while all three run at the same time.
      generateBodyFor[draftId] =
        `{"type":"attempt.started","attemptId":"${draftId}-1"}\n` +
        `{"type":"stage.started","stage":"${stageByDraft[draftId]}","ordinal":2,"total":9}\n`;
    }
    const generationProgress: Record<string, unknown> = {};
    const state: RouteState = {
      drafts,
      generateBody: "",
      generateBodyFor,
      onGenerate: (draftId) => {
        drafts[draftId] = askGusDraft({
          draftId,
          status: "GENERATING",
          revision: 1,
          presentation: null,
          gameplay: null,
        });
        generationProgress[draftId] = {
          draftId,
          active: true,
          attempt: {
            attemptId: `${draftId}-1`,
            draftId,
            kind: "INITIAL",
            sourceRevision: 1,
            status: "RUNNING",
            currentStage: stageByDraft[draftId],
            stages: [
              {
                stage: stageByDraft[draftId],
                status: "RUNNING",
                retryCount: 0,
                startedAt: "2026-08-04T00:00:00Z",
                finishedAt: null,
                error: null,
              },
            ],
            startedAt: "2026-08-04T00:00:00Z",
            finishedAt: null,
            error: null,
          },
        };
      },
      generationProgress,
    };

    const pageA = await context.newPage();
    const pageB = await context.newPage();
    const pageC = await context.newPage();
    await installApiRoutes(pageA, state);
    await installApiRoutes(pageB, state);
    await installApiRoutes(pageC, state);

    await pageA.goto("/drafts/draft-a");
    await pageB.goto("/drafts/draft-b");
    await pageC.goto("/drafts/draft-c");
    await expect(pageA.getByRole("button", { name: "开始生成" })).toBeVisible();
    await expect(pageB.getByRole("button", { name: "开始生成" })).toBeVisible();
    await expect(pageC.getByRole("button", { name: "开始生成" })).toBeVisible();

    await pageA.getByRole("button", { name: "开始生成" }).click();
    await pageB.getByRole("button", { name: "开始生成" }).click();
    await pageC.getByRole("button", { name: "开始生成" }).click();

    // Each page shows its own stage while all three generate; no stage bleeds.
    // (The stage timeline lists every stage, so the current-stage aria label
    // is the precise per-page discriminator.)
    await expect(pageA.getByLabel("当前阶段：识别菜品")).toBeVisible();
    await expect(pageB.getByLabel("当前阶段：匹配游戏原料")).toBeVisible();
    await expect(pageC.getByLabel("当前阶段：整理料理数据")).toBeVisible();
    await expect(pageA.getByLabel("当前阶段：匹配游戏原料")).toHaveCount(0);
    await expect(pageC.getByLabel("当前阶段：识别菜品")).toHaveCount(0);

    // Cancelling page-a leaves the other two streaming their own stages.
    await pageA.getByRole("button", { name: "取消生成" }).click();
    await expect(pageA.getByText("已取消生成。")).toBeVisible();
    await expect(pageB.getByLabel("当前阶段：匹配游戏原料")).toBeVisible();
    await expect(pageC.getByLabel("当前阶段：整理料理数据")).toBeVisible();

    // Refreshing page-b restores its own stage from the per-draft progress
    // snapshot; pages a and c are unaffected.
    await pageB.reload();
    await expect(pageB.getByLabel("当前阶段：匹配游戏原料")).toBeVisible();
    await expect(pageB.getByRole("button", { name: "取消生成" })).toBeVisible();
    await expect(pageA.getByText("已取消生成。")).toBeVisible();
    await expect(pageC.getByLabel("当前阶段：整理料理数据")).toBeVisible();
  });
});
