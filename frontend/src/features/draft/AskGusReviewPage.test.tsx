import "@testing-library/jest-dom/vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { setupServer } from "msw/node";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterAll, afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import { catalogs } from "../../i18n/copy";
import {
  applyTerminalSnapshot,
  resetGenerationStore,
} from "../generation/generationStore";
import { AskGusReviewPage } from "./AskGusReviewPage";

const copy = catalogs["zh-CN"];

const server = setupServer();

const successfulProgress = (attemptOverrides: Record<string, unknown> = {}) => ({
  draftId: "draft-1",
  active: false,
  attempt: {
    attemptId: "a-1",
    draftId: "draft-1",
    kind: "INITIAL",
    sourceRevision: 3,
    status: "SUCCEEDED",
    currentStage: null,
    stages: [],
    totalStages: 9,
    startedAt: "2026-08-25T00:00:00.000Z",
    finishedAt: "2026-08-25T00:00:09.500Z",
    error: null,
    ...attemptOverrides,
  },
});

beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
beforeEach(() => {
  resetGenerationStore();
  server.use(
    http.get("/api/v1/drafts/:draft_id/generation", () =>
      HttpResponse.json({ draftId: "draft-1", active: false, attempt: null }),
    ),
  );
});
afterEach(() => {
  server.resetHandlers();
  vi.restoreAllMocks();
});
afterAll(() => server.close());

const provenance = {
  mode: "ASK_GUS",
  authorityByField: {},
  visionModel: "vision-model",
  textModel: null,
  imageModel: null,
  promptVersions: {},
  generationSource: "FRESH_GENERATION",
  canonicalDishSignature: null,
  cacheEligibility: true,
};

const source = { originalImageAssetId: "asset-1", contextText: null, language: "zh-CN" };

function askGusDraft(overrides: Record<string, unknown> = {}) {
  return {
    draftId: "draft-1",
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
    provenance,
    lastError: null,
    createdAt: "2026-08-04T00:00:00Z",
    updatedAt: "2026-08-04T00:00:00Z",
    archivedDishId: null,
    ...overrides,
  };
}

function renderPage(
  queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  }),
) {
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={["/drafts/draft-1"]}>
        <Routes>
          <Route path="/drafts/:draftId" element={<AskGusReviewPage />} />
          <Route path="/cookbook/:dishId" element={<div>cookbook page</div>} />
          <Route path="/settings" element={<div>settings page</div>} />
          <Route path="/" element={<div>home page</div>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("ask gus review", () => {
  it("renders preview and icon assets through the asset endpoint", async () => {
    server.use(
      http.get("/api/v1/drafts/:draft_id", () =>
        HttpResponse.json(
          askGusDraft({
            visuals: {
              previewAssetId: "preview-1",
              icon16AssetId: "icon-1",
            },
          }),
        ),
      ),
    );
    renderPage();

    expect(await screen.findByRole("img", { name: "南瓜汤预览" })).toHaveAttribute(
      "src",
      "/api/v1/assets/preview-1",
    );
    expect(screen.getByRole("img", { name: "南瓜汤像素图标" })).toHaveAttribute(
      "src",
      "/api/v1/assets/icon-1",
    );
  });

  it("restores neutral timing on a REVIEWABLE mount without starting generation", async () => {
    const generateSpy = vi.fn();
    server.use(
      http.get("/api/v1/drafts/:draft_id", () => HttpResponse.json(askGusDraft())),
      http.get("/api/v1/drafts/:draft_id/generation", () =>
        HttpResponse.json(successfulProgress()),
      ),
      http.post("/api/v1/drafts/:draft_id/generate", generateSpy),
    );
    renderPage();

    expect(
      await screen.findByRole("status", { name: "本次生成用时 9.5 秒" }),
    ).toBeVisible();
    expect(screen.queryByText("Gus 的灵感")).toBeNull();
    expect(generateSpy).not.toHaveBeenCalled();
  });

  it("uses the special Gus story only for a canonical-reused result", async () => {
    server.use(
      http.get("/api/v1/drafts/:draft_id", () =>
        HttpResponse.json(
          askGusDraft({
            provenance: { ...provenance, generationSource: "CANONICAL_REUSED" },
          }),
        ),
      ),
      http.get("/api/v1/drafts/:draft_id/generation", () =>
        HttpResponse.json(successfulProgress()),
      ),
    );
    renderPage();

    expect(
      await screen.findByText(
        "嗯，这道菜声名远扬，我好像在哪吃过它。于是我灵感涌现，加快了我的鉴定速度。",
      ),
    ).toBeVisible();
    expect(screen.getByText("Gus 的灵感")).toBeVisible();
    expect(screen.getByRole("status")).toHaveAccessibleName(
      "Gus 的灵感，本次生成用时 9.5 秒",
    );
  });

  it("does not pair full-regeneration timing with stale canonical provenance", async () => {
    let draftCallCount = 0;
    let releaseDraftRefresh!: () => void;
    const draftRefresh = new Promise<void>((resolve) => {
      releaseDraftRefresh = resolve;
    });
    let progressCallCount = 0;
    server.use(
      http.get("/api/v1/drafts/:draft_id", async () => {
        draftCallCount += 1;
        if (draftCallCount === 1) {
          return HttpResponse.json(
            askGusDraft({
              provenance: { ...provenance, generationSource: "CANONICAL_REUSED" },
            }),
          );
        }
        await draftRefresh;
        return HttpResponse.json(
          askGusDraft({
            revision: 4,
            provenance: { ...provenance, generationSource: "FRESH_GENERATION" },
          }),
        );
      }),
      http.get("/api/v1/drafts/:draft_id/generation", () => {
        progressCallCount += 1;
        return HttpResponse.json(
          progressCallCount === 1
            ? { draftId: "draft-1", active: false, attempt: null }
            : successfulProgress({
                attemptId: "full-1",
                kind: "FULL_REGENERATE",
                sourceRevision: 3,
              }),
        );
      }),
      http.post("/api/v1/drafts/:draft_id/generate", () =>
        new Response(
          '{"type":"attempt.started","attemptId":"full-1"}\n' +
            '{"type":"attempt.succeeded","attemptId":"full-1","draftRevision":4,"draft":{}}\n',
          { status: 200, headers: { "Content-Type": "application/x-ndjson" } },
        ),
      ),
    );
    renderPage();

    fireEvent.click(await screen.findByRole("button", { name: copy.fullRegenerate }));
    await waitFor(() => expect(draftCallCount).toBe(2));
    expect(screen.queryByText("嗯，这道菜声名远扬，我好像在哪吃过它。于是我灵感涌现，加快了我的鉴定速度。")).toBeNull();

    releaseDraftRefresh();
    expect(
      await screen.findByRole("status", { name: "本次生成用时 9.5 秒" }),
    ).toBeVisible();
    expect(screen.queryByText("Gus 的灵感")).toBeNull();
  });

  it("waits for a cached canonical DraftView to refresh before mount timing", async () => {
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    queryClient.setQueryData(
      ["draft", "draft-1"],
      askGusDraft({
        provenance: { ...provenance, generationSource: "CANONICAL_REUSED" },
      }),
    );
    applyTerminalSnapshot("draft-1", {
      attemptId: "canonical-old",
      draftId: "draft-1",
      kind: "INITIAL",
      sourceRevision: 2,
      status: "SUCCEEDED",
      currentStage: null,
      stages: [],
      totalStages: 9,
      startedAt: "2026-08-25T00:00:00.000Z",
      finishedAt: "2026-08-25T00:00:08.000Z",
      error: null,
    });
    let releaseDraftRefresh!: () => void;
    const draftRefreshGate = new Promise<void>((resolve) => {
      releaseDraftRefresh = resolve;
    });
    const progressHandler = vi.fn(() =>
      HttpResponse.json(
        successfulProgress({
          attemptId: "fresh-after-cache",
          kind: "FULL_REGENERATE",
          sourceRevision: 3,
        }),
      ),
    );
    server.use(
      http.get("/api/v1/drafts/:draft_id", async () => {
        await draftRefreshGate;
        return HttpResponse.json(
          askGusDraft({
            revision: 4,
            provenance: { ...provenance, generationSource: "FRESH_GENERATION" },
          }),
        );
      }),
      http.get("/api/v1/drafts/:draft_id/generation", progressHandler),
    );
    renderPage(queryClient);

    await waitFor(() => expect(progressHandler).toHaveBeenCalledTimes(1));
    await waitFor(() => expect(screen.queryByText("Gus 的灵感")).toBeNull());
    expect(
      screen.queryByRole("status", { name: "本次生成用时 9.5 秒" }),
    ).toBeNull();

    releaseDraftRefresh();
    expect(
      await screen.findByRole("status", { name: "本次生成用时 9.5 秒" }),
    ).toBeVisible();
    expect(screen.queryByText("Gus 的灵感")).toBeNull();
  });

  it("does not show timing for a failed terminal attempt", async () => {
    server.use(
      http.get("/api/v1/drafts/:draft_id", () => HttpResponse.json(askGusDraft())),
      http.get("/api/v1/drafts/:draft_id/generation", () =>
        HttpResponse.json(
          successfulProgress({
            status: "FAILED",
            error: {
              code: "PTS_GEN_VALIDATION_FAILED",
              message: "生成结果未通过校验。",
              retryable: false,
              requestId: "req-1",
            },
          }),
        ),
      ),
    );
    renderPage();

    await screen.findByRole("button", { name: copy.fullRegenerate });
    expect(screen.queryByRole("status")).toBeNull();
  });

  it("offers full regeneration but no partial visual actions", async () => {
    server.use(
      http.get("/api/v1/drafts/:draft_id", () => HttpResponse.json(askGusDraft())),
    );
    renderPage();

    expect(
      await screen.findByRole("button", { name: copy.fullRegenerate }),
    ).toBeVisible();
    expect(
      screen.queryByRole("button", { name: /重新生成图标|重新生成预览/ }),
    ).toBeNull();
    // F19-3-001: the convert-to-blueprint entry was removed from this page.
    expect(screen.queryByRole("button", { name: "进入料理蓝图" })).toBeNull();
    expect(screen.getByRole("button", { name: copy.archiveDish })).toBeVisible();
    expect(screen.getByRole("button", { name: copy.rejectDraft })).toBeVisible();
  });

  it("keeps the old result visible while full regeneration streams", async () => {
    server.use(
      http.get("/api/v1/drafts/:draft_id", () => HttpResponse.json(askGusDraft())),
      http.post("/api/v1/drafts/:draft_id/generate", () =>
        new Response(
          '{"type":"attempt.started","attemptId":"a-1"}\n{"type":"stage.started","stage":"DISH_ANALYSIS","ordinal":2,"total":9}\n',
          { status: 200, headers: { "Content-Type": "application/x-ndjson" } },
        ),
      ),
    );
    renderPage();

    await screen.findByRole("button", { name: copy.fullRegenerate });
    expect(screen.getByText("南瓜汤")).toBeVisible();

    fireEvent.click(screen.getByRole("button", { name: copy.fullRegenerate }));

    expect(await screen.findByText(copy.preparingNewResult)).toBeVisible();
    expect(screen.getByText("南瓜汤")).toBeVisible();
  });

  it("restores the old result when full regeneration fails", async () => {
    server.use(
      http.get("/api/v1/drafts/:draft_id", () => HttpResponse.json(askGusDraft())),
      http.post("/api/v1/drafts/:draft_id/generate", () =>
        new Response(
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
          { status: 200, headers: { "Content-Type": "application/x-ndjson" } },
        ),
      ),
    );
    renderPage();

    await screen.findByRole("button", { name: copy.fullRegenerate });
    fireEvent.click(screen.getByRole("button", { name: copy.fullRegenerate }));

    expect(await screen.findByText("生成结果未通过校验。")).toBeVisible();
    expect(screen.getByText("南瓜汤")).toBeVisible();
    expect(screen.getByRole("button", { name: copy.retryGeneration })).toBeVisible();
  });

  it("archives the draft with an Idempotency-Key header", async () => {
    const archiveSpy = vi.fn((info: { request: Request }) => {
      void info;
      return HttpResponse.json(
        {
          dishId: "dish-1",
          displayName: "南瓜汤",
          status: "ARCHIVED",
          mode: "ASK_GUS",
          archivedAt: "2026-08-04T00:00:00Z",
          originalImageAssetId: "asset-1",
        },
        { status: 201 },
      );
    });
    server.use(
      http.get("/api/v1/drafts/:draft_id", () => HttpResponse.json(askGusDraft())),
      http.post("/api/v1/drafts/:draft_id/archive", archiveSpy),
    );
    renderPage();

    fireEvent.click(await screen.findByRole("button", { name: copy.archiveDish }));

    await waitFor(() => expect(archiveSpy).toHaveBeenCalledTimes(1));
    const request = archiveSpy.mock.calls[0]?.[0]?.request as Request;
    expect(request.headers.get("Idempotency-Key")).toBeTruthy();
    expect(await screen.findByText("cookbook page")).toBeVisible();
  });

  it("rejects the draft after confirmation and navigates home", async () => {
    const discardSpy = vi.fn(() => new Response(null, { status: 204 }));
    server.use(
      http.get("/api/v1/drafts/:draft_id", () => HttpResponse.json(askGusDraft())),
      http.post("/api/v1/drafts/:draft_id/discard", discardSpy),
    );
    renderPage();

    fireEvent.click(await screen.findByRole("button", { name: copy.rejectDraft }));

    const dialog = screen.getByRole("dialog", { name: "拒绝这份草稿？" });
    fireEvent.click(within(dialog).getByRole("button", { name: copy.rejectDraft }));
    await waitFor(() => expect(discardSpy).toHaveBeenCalledTimes(1));
    expect(await screen.findByText("home page")).toBeVisible();
  });

  it("does not reject when confirmation is cancelled", async () => {
    const discardSpy = vi.fn(() => new Response(null, { status: 204 }));
    server.use(
      http.get("/api/v1/drafts/:draft_id", () => HttpResponse.json(askGusDraft())),
      http.post("/api/v1/drafts/:draft_id/discard", discardSpy),
    );
    renderPage();

    fireEvent.click(await screen.findByRole("button", { name: copy.rejectDraft }));

    const dialog = screen.getByRole("dialog", { name: "拒绝这份草稿？" });
    fireEvent.click(within(dialog).getByRole("button", { name: copy.cancelDelete }));
    expect(discardSpy).not.toHaveBeenCalled();
    expect(screen.queryByText("home page")).toBeNull();
  });

  it("starts an initial generation for a fresh DRAFT", async () => {
    const getSpy = vi
      .fn()
      .mockReturnValueOnce(
        HttpResponse.json(askGusDraft({ status: "DRAFT", revision: 1, presentation: null, gameplay: null })),
      )
      .mockReturnValueOnce(HttpResponse.json(askGusDraft({ status: "REVIEWABLE", revision: 3 })));
    server.use(
      http.get("/api/v1/drafts/:draft_id", getSpy),
      http.post("/api/v1/drafts/:draft_id/generate", () =>
        new Response(
          '{"type":"attempt.started","attemptId":"a-1"}\n{"type":"attempt.succeeded","attemptId":"a-1","draftRevision":3,"draft":{}}\n',
          { status: 200, headers: { "Content-Type": "application/x-ndjson" } },
        ),
      ),
    );
    renderPage();

    fireEvent.click(await screen.findByRole("button", { name: copy.startGeneration }));

    expect(
      await screen.findByRole("button", { name: copy.fullRegenerate }),
    ).toBeVisible();
    expect(getSpy).toHaveBeenCalledTimes(2);
  });

  it("offers a retry entry for a FAILED draft", async () => {
    server.use(
      http.get("/api/v1/drafts/:draft_id", () =>
        HttpResponse.json(
          askGusDraft({
            status: "FAILED",
            lastError: {
              code: "PTS_GEN_VALIDATION_FAILED",
              message: "生成结果未通过校验。",
              retryable: false,
              requestId: "req-1",
              occurredAt: "2026-08-04T00:00:00Z",
            },
          }),
        ),
      ),
    );
    renderPage();

    await screen.findByRole("button", { name: copy.retryGeneration });
    expect(screen.queryByRole("button", { name: copy.startGeneration })).toBeNull();
  });

  it("retries a FAILED draft to a successful reviewable result", async () => {
    const getSpy = vi
      .fn()
      .mockReturnValueOnce(
        HttpResponse.json(
          askGusDraft({
            status: "FAILED",
            lastError: {
              code: "PTS_GEN_VALIDATION_FAILED",
              message: "生成结果未通过校验。",
              retryable: false,
              requestId: "req-1",
              occurredAt: "2026-08-04T00:00:00Z",
            },
          }),
        ),
      )
      .mockReturnValueOnce(HttpResponse.json(askGusDraft({ status: "REVIEWABLE", revision: 3 })));
    server.use(
      http.get("/api/v1/drafts/:draft_id", getSpy),
      http.post("/api/v1/drafts/:draft_id/generate", () =>
        new Response(
          '{"type":"attempt.started","attemptId":"a-1"}\n{"type":"attempt.succeeded","attemptId":"a-1","draftRevision":3,"draft":{}}\n',
          { status: 200, headers: { "Content-Type": "application/x-ndjson" } },
        ),
      ),
    );
    renderPage();

    fireEvent.click(await screen.findByRole("button", { name: copy.retryGeneration }));

    expect(
      await screen.findByRole("button", { name: copy.fullRegenerate }),
    ).toBeVisible();
    expect(getSpy).toHaveBeenCalledTimes(2);
  });

  it("shows the error with a retry entry when initial generation fails", async () => {
    server.use(
      http.get("/api/v1/drafts/:draft_id", () =>
        HttpResponse.json(
          askGusDraft({ status: "DRAFT", revision: 1, presentation: null, gameplay: null }),
        ),
      ),
      http.post("/api/v1/drafts/:draft_id/generate", () =>
        new Response(
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
          { status: 200, headers: { "Content-Type": "application/x-ndjson" } },
        ),
      ),
    );
    renderPage();

    fireEvent.click(await screen.findByRole("button", { name: copy.startGeneration }));

    expect(await screen.findByText("生成结果未通过校验。")).toBeVisible();
    expect(screen.getByRole("button", { name: copy.retryGeneration })).toBeVisible();
  });

  it("persists personal takeover before starting the replacement generation", async () => {
    const requestOrder: string[] = [];
    let generateCalls = 0;
    server.use(
      http.get("/api/v1/drafts/:draft_id", () =>
        HttpResponse.json(
          askGusDraft({ status: "DRAFT", revision: 1, presentation: null, gameplay: null }),
        ),
      ),
      http.put("/api/v1/settings/provider/trial/preference", async ({ request }) => {
        const body = (await request.json()) as { mode?: string };
        requestOrder.push(`preference:${body.mode ?? ""}`);
        return HttpResponse.json({
          available: true,
          enabled: false,
          claimedAttempts: 0,
          limit: 2,
          remaining: 2,
          providerPreference: "PERSONAL",
        });
      }),
      http.post("/api/v1/drafts/:draft_id/generate", () => {
        generateCalls += 1;
        requestOrder.push("generate");
        const body =
          generateCalls === 1
            ? JSON.stringify({
                type: "attempt.failed",
                attemptId: "a-1",
                error: {
                  code: "PTS_TRIAL_SERVICE_UNAVAILABLE",
                  message: "试用服务失败：provider=https://hidden.example key=sk-secret",
                  retryable: true,
                  requestId: "req-1",
                  recommendedAction: "CHECK_LOCAL_CONFIGURATION",
                  details: { personalProviderConfigured: true },
                },
              }) + "\n"
            : '{"type":"attempt.started","attemptId":"a-2"}\n{"type":"attempt.succeeded","attemptId":"a-2","draftRevision":2,"draft":{}}\n';
        return new Response(body, {
          status: 200,
          headers: { "Content-Type": "application/x-ndjson" },
        });
      }),
    );
    renderPage();

    fireEvent.click(await screen.findByRole("button", { name: copy.startGeneration }));
    expect(await screen.findByRole("button", { name: copy.usePersonalProvider })).toBeVisible();
    expect(generateCalls).toBe(1);

    fireEvent.click(screen.getByRole("button", { name: copy.usePersonalProvider }));

    await waitFor(() => expect(generateCalls).toBe(2));
    expect(requestOrder).toEqual([
      "generate",
      "preference:PERSONAL",
      "generate",
    ]);
  });

  it("does not start generation when personal takeover preference PUT fails", async () => {
    let generateCalls = 0;
    server.use(
      http.get("/api/v1/drafts/:draft_id", () =>
        HttpResponse.json(
          askGusDraft({ status: "DRAFT", revision: 1, presentation: null, gameplay: null }),
        ),
      ),
      http.put(
        "/api/v1/settings/provider/trial/preference",
        () => HttpResponse.json({ error: { code: "PTS_SETTINGS_FAILED" } }, { status: 503 }),
      ),
      http.post("/api/v1/drafts/:draft_id/generate", () => {
        generateCalls += 1;
        return new Response(
          JSON.stringify({
            type: "attempt.failed",
            attemptId: "a-1",
            error: {
              code: "PTS_TRIAL_SERVICE_UNAVAILABLE",
              message: "公共试用失败",
              retryable: true,
              requestId: "req-1",
              recommendedAction: "CHECK_LOCAL_CONFIGURATION",
              details: { personalProviderConfigured: true },
            },
          }) + "\n",
          { status: 200, headers: { "Content-Type": "application/x-ndjson" } },
        );
      }),
    );
    renderPage();

    fireEvent.click(await screen.findByRole("button", { name: copy.startGeneration }));
    fireEvent.click(await screen.findByRole("button", { name: copy.usePersonalProvider }));

    expect(await screen.findByText(copy.providerPreferenceFailed)).toBeVisible();
    expect(generateCalls).toBe(1);
  });

  it("persists personal preference before navigating to settings when configuration is needed", async () => {
    const requestOrder: string[] = [];
    server.use(
      http.get("/api/v1/drafts/:draft_id", () =>
        HttpResponse.json(
          askGusDraft({ status: "DRAFT", revision: 1, presentation: null, gameplay: null }),
        ),
      ),
      http.put("/api/v1/settings/provider/trial/preference", async ({ request }) => {
        const body = (await request.json()) as { mode?: string };
        requestOrder.push(`preference:${body.mode ?? ""}`);
        return HttpResponse.json({
          available: true,
          enabled: false,
          claimedAttempts: 0,
          limit: 2,
          remaining: 2,
          providerPreference: "PERSONAL",
        });
      }),
      http.post("/api/v1/drafts/:draft_id/generate", () => {
        requestOrder.push("generate");
        return new Response(
          JSON.stringify({
            type: "attempt.failed",
            attemptId: "a-1",
            error: {
              code: "PTS_TRIAL_SERVICE_UNAVAILABLE",
              message: "公共试用失败",
              retryable: true,
              requestId: "req-1",
              recommendedAction: "CHECK_LOCAL_CONFIGURATION",
              details: { personalProviderConfigured: false },
            },
          }) + "\n",
          { status: 200, headers: { "Content-Type": "application/x-ndjson" } },
        );
      }),
    );
    renderPage();

    fireEvent.click(await screen.findByRole("button", { name: copy.startGeneration }));
    fireEvent.click(
      await screen.findByRole("button", { name: copy.configurePersonalProvider }),
    );

    expect(await screen.findByText("settings page")).toBeVisible();
    expect(requestOrder).toEqual(["generate", "preference:PERSONAL"]);
  });

  it("does not show the no-gameplay-yet hint on an empty ask-gus draft", async () => {
    server.use(
      http.get("/api/v1/drafts/:draft_id", () =>
        HttpResponse.json(
          askGusDraft({ status: "DRAFT", revision: 1, presentation: null, gameplay: null }),
        ),
      ),
    );
    renderPage();

    await screen.findByRole("button", { name: copy.startGeneration });
    // F19-4-001: the no-gameplay-yet hint was removed.
    expect(screen.queryByText("尚未填写玩法字段。")).toBeNull();
    expect(screen.getByText(copy.gusWaitingTitle)).toBeVisible();
    expect(screen.getByText(copy.gusWaitingMessage)).toBeVisible();
  });

  it("offers a cancel entry in the running banner for a GENERATING draft", async () => {
    const cancelSpy = vi.fn(() => new Response(null, { status: 202 }));
    server.use(
      http.get("/api/v1/drafts/:draft_id", () =>
        HttpResponse.json(askGusDraft({ status: "GENERATING", revision: 3 })),
      ),
      http.post("/api/v1/drafts/:draft_id/cancel", cancelSpy),
    );
    renderPage();

    await screen.findByText(copy.generationInProgress);
    fireEvent.click(screen.getByRole("button", { name: copy.cancelGeneration }));

    await waitFor(() => expect(cancelSpy).toHaveBeenCalledTimes(1));
  });
});
