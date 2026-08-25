import { expect, test, type Page, type Route } from "@playwright/test";

/**
 * Task 36 browser contract checks. Every session/API request is intercepted;
 * the spec never starts a backend or calls a Provider.
 */

type DraftMode = "ASK_GUS" | "BLUEPRINT";
type GenerationSource = "CANONICAL_REUSED" | "FRESH_GENERATION" | "USER_AUTHORED";

type Draft = Record<string, unknown> & {
  draftId: string;
  mode: DraftMode;
  status: string;
  provenance: { generationSource: GenerationSource };
};

type MemoryRouteState = {
  drafts: Record<string, Draft>;
  progress: Record<string, Record<string, unknown>>;
  unhandledApiRequests: string[];
};

const ONE_PIXEL_PNG = Buffer.from(
  "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=",
  "base64",
);

const source = {
  originalImageAssetId: "asset-original",
  contextText: null,
  language: "zh-CN",
};

function draft(
  draftId: string,
  mode: DraftMode,
  generationSource: GenerationSource,
): Draft {
  return {
    draftId,
    mode,
    baseTemplateVersion: mode === "BLUEPRINT" ? "blueprint-v1" : null,
    status: "REVIEWABLE",
    revision: 3,
    source,
    presentation: {
      displayName: mode === "BLUEPRINT" ? "南瓜蓝图" : "南瓜汤",
      internalName: mode === "BLUEPRINT" ? "PumpkinBlueprint" : "PumpkinSoup",
      categoryLabel: "汤类",
      description: "香甜的南瓜汤。",
      gusComment: generationSource === "CANONICAL_REUSED" ? "这道菜很有鹈鹕镇的味道。" : null,
      tags: ["秋日"],
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
    visuals: {
      generatedArtAssetId: null,
      previewAssetId: `preview-${draftId}`,
      iconSourceAssetId: `icon-source-${draftId}`,
      icon16AssetId: `icon-16-${draftId}`,
      sourceRevision: 3,
      promptVersion: "fixture-v1",
    },
    provenance: {
      mode,
      authorityByField: {},
      visionModel: mode === "ASK_GUS" ? "fixture-vision" : null,
      textModel: null,
      imageModel: null,
      promptVersions: {},
      generationSource,
      canonicalDishSignature: generationSource === "CANONICAL_REUSED" ? "fixture-signature" : null,
      cacheEligibility: mode === "ASK_GUS",
    },
    lastError: null,
    createdAt: "2026-08-25T00:00:00Z",
    updatedAt: "2026-08-25T00:00:00Z",
    archivedDishId: null,
  };
}

function terminalProgress(
  draftId: string,
  startedAt: string,
  finishedAt: string,
  kind: "INITIAL" | "BLUEPRINT_PREVIEW" = "INITIAL",
): Record<string, unknown> {
  return {
    draftId,
    active: false,
    attempt: {
      attemptId: `${draftId}-attempt-1`,
      draftId,
      kind,
      sourceRevision: 3,
      status: "SUCCEEDED",
      currentStage: null,
      stages: [],
      totalStages: kind === "BLUEPRINT_PREVIEW" ? 3 : 9,
      startedAt,
      finishedAt,
      error: null,
    },
  };
}

async function installRoutes(page: Page, state: MemoryRouteState): Promise<void> {
  await page.route("**/*", async (route: Route) => {
    const request = route.request();
    const url = new URL(request.url());
    const { pathname } = url;
    const method = request.method();
    const isApiRequest = pathname.startsWith("/api/") || pathname.startsWith("/session/") || pathname === "/app/heartbeat";

    if (!isApiRequest) {
      await route.continue();
      return;
    }

    if (pathname === "/session/status") {
      await route.fulfill({ status: 200, headers: { "X-PTS-CSRF": "task36-csrf" }, body: "" });
      return;
    }
    if (pathname === "/session/bootstrap") {
      await route.fulfill({ status: 204, headers: { "X-PTS-CSRF": "task36-csrf" } });
      return;
    }
    if (pathname === "/app/heartbeat") {
      await route.fulfill({ status: 204 });
      return;
    }
    if (pathname === "/api/v1/health") {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ status: "ok", app: "PelicanTownSpecials", apiVersion: "v1" }),
      });
      return;
    }
    if (pathname.startsWith("/api/v1/assets/")) {
      await route.fulfill({ status: 200, contentType: "image/png", body: ONE_PIXEL_PNG });
      return;
    }

    const generationMatch = pathname.match(/^\/api\/v1\/drafts\/([^/]+)\/generation$/);
    if (generationMatch && method === "GET") {
      const draftId = decodeURIComponent(generationMatch[1]);
      const progress = state.progress[draftId];
      if (!progress) {
        await route.fulfill({ status: 404, contentType: "application/json", body: "{}" });
        return;
      }
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(progress) });
      return;
    }

    const draftMatch = pathname.match(/^\/api\/v1\/drafts\/([^/]+)$/);
    if (draftMatch && method === "GET") {
      const draftId = decodeURIComponent(draftMatch[1]);
      const currentDraft = state.drafts[draftId];
      if (!currentDraft) {
        await route.fulfill({ status: 404, contentType: "application/json", body: "{}" });
        return;
      }
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(currentDraft) });
      return;
    }

    // Keep mutation routes intercepted as well, even though these assertions
    // only exercise read/refresh/route-restoration behavior.
    if (draftMatch && ["PATCH", "POST"].includes(method)) {
      const draftId = decodeURIComponent(draftMatch[1]);
      const currentDraft = state.drafts[draftId];
      await route.fulfill({
        status: currentDraft ? 200 : 404,
        contentType: "application/json",
        body: JSON.stringify(currentDraft ?? {}),
      });
      return;
    }

    const actionMatch = pathname.match(/^\/api\/v1\/drafts\/([^/]+)\/([^/]+)$/);
    if (actionMatch && ["PATCH", "POST"].includes(method)) {
      const draftId = decodeURIComponent(actionMatch[1]);
      const currentDraft = state.drafts[draftId];
      await route.fulfill({
        status: currentDraft ? (actionMatch[2] === "archive" ? 201 : 204) : 404,
        contentType: actionMatch[2] === "discard" ? undefined : "application/json",
        body: actionMatch[2] === "discard" ? "" : JSON.stringify(currentDraft ?? {}),
      });
      return;
    }

    const requestLabel = `${method} ${pathname}`;
    state.unhandledApiRequests.push(requestLabel);
    await route.fulfill({
      status: 500,
      contentType: "application/json",
      body: JSON.stringify({ error: { code: "TASK36_UNHANDLED_ROUTE", message: requestLabel } }),
    });
  });
}

async function assertNoTechnicalTerms(page: Page): Promise<void> {
  const body = await page.locator("body").innerText();
  expect(body).not.toMatch(
    /Canonical|Registry|SQLite|internalName|confidence|CACHE_REUSED|FRESH_GENERATION|generationSource/i,
  );
}

function stateForMemoryStories(): MemoryRouteState {
  return {
    drafts: {
      hit: draft("hit", "ASK_GUS", "CANONICAL_REUSED"),
      fresh: draft("fresh", "ASK_GUS", "FRESH_GENERATION"),
      blueprint: draft("blueprint", "BLUEPRINT", "USER_AUTHORED"),
    },
    progress: {
      hit: terminalProgress("hit", "2026-08-25T00:00:00Z", "2026-08-25T00:00:08Z"),
      fresh: terminalProgress("fresh", "2026-08-25T00:00:00Z", "2026-08-25T00:00:12Z"),
      blueprint: terminalProgress(
        "blueprint",
        "2026-08-25T00:00:00Z",
        "2026-08-25T00:00:06Z",
        "BLUEPRINT_PREVIEW",
      ),
    },
    unhandledApiRequests: [],
  };
}

test.describe("generation memory user stories", () => {
  test("shows Gus recognition timing and restores it after refresh", async ({ page }) => {
    const state = stateForMemoryStories();
    await installRoutes(page, state);

    await page.goto("/drafts/hit");
    await expect(page.getByRole("heading", { name: "南瓜汤" })).toBeVisible();
    await expect(page.getByText("Gus 的灵感")).toBeVisible();
    await expect(page.getByText("本次生成用时 8.0 秒")).toBeVisible();
    await assertNoTechnicalTerms(page);

    await page.reload();
    await expect(page.getByText("Gus 的灵感")).toBeVisible();
    await expect(page.getByText("本次生成用时 8.0 秒")).toBeVisible();
    await assertNoTechnicalTerms(page);
    expect(state.unhandledApiRequests).toEqual([]);
  });

  test("keeps fresh and Blueprint timing neutral while restoring routes", async ({ page }) => {
    const state = stateForMemoryStories();
    await installRoutes(page, state);

    await page.goto("/drafts/fresh");
    await expect(page.getByRole("heading", { name: "南瓜汤" })).toBeVisible();
    await expect(page.getByText("本次生成", { exact: true })).toBeVisible();
    await expect(page.getByText("本次生成用时 12 秒")).toBeVisible();
    await expect(page.getByText("Gus 的灵感")).toHaveCount(0);
    await assertNoTechnicalTerms(page);

    await page.goto("/drafts/blueprint");
    await expect(page.getByRole("heading", { name: "编辑料理蓝图" })).toBeVisible();
    await expect(page.getByText("本次生成", { exact: true })).toBeVisible();
    await expect(page.getByText("本次生成用时 6.0 秒")).toBeVisible();
    await expect(page.getByText("Gus 的灵感")).toHaveCount(0);
    await assertNoTechnicalTerms(page);
    expect(state.unhandledApiRequests).toEqual([]);
  });
});
