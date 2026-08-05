import "@testing-library/jest-dom/vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { setupServer } from "msw/node";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterAll, afterEach, beforeAll, describe, expect, it, vi } from "vitest";
import { PRODUCT_COPY } from "../../i18n/copy";
import { AskGusReviewPage } from "./AskGusReviewPage";

const copy = PRODUCT_COPY.zh;

const server = setupServer();

beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
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

function renderPage() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={["/drafts/draft-1"]}>
        <Routes>
          <Route path="/drafts/:draftId" element={<AskGusReviewPage />} />
          <Route path="/cookbook/:dishId" element={<div>cookbook page</div>} />
          <Route path="/" element={<div>home page</div>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("ask gus review", () => {
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
    expect(screen.getByRole("button", { name: copy.convertToBlueprint })).toBeVisible();
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
    const confirmSpy = vi.spyOn(window, "confirm").mockReturnValue(true);
    const discardSpy = vi.fn(() => new Response(null, { status: 204 }));
    server.use(
      http.get("/api/v1/drafts/:draft_id", () => HttpResponse.json(askGusDraft())),
      http.post("/api/v1/drafts/:draft_id/discard", discardSpy),
    );
    renderPage();

    fireEvent.click(await screen.findByRole("button", { name: copy.rejectDraft }));

    expect(confirmSpy).toHaveBeenCalledWith(copy.discardDraftConfirm);
    await waitFor(() => expect(discardSpy).toHaveBeenCalledTimes(1));
    expect(await screen.findByText("home page")).toBeVisible();
  });

  it("does not reject when confirmation is cancelled", async () => {
    const confirmSpy = vi.spyOn(window, "confirm").mockReturnValue(false);
    const discardSpy = vi.fn(() => new Response(null, { status: 204 }));
    server.use(
      http.get("/api/v1/drafts/:draft_id", () => HttpResponse.json(askGusDraft())),
      http.post("/api/v1/drafts/:draft_id/discard", discardSpy),
    );
    renderPage();

    fireEvent.click(await screen.findByRole("button", { name: copy.rejectDraft }));

    expect(confirmSpy).toHaveBeenCalledWith(copy.discardDraftConfirm);
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
});
