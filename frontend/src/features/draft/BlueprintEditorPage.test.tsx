import "@testing-library/jest-dom/vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { setupServer } from "msw/node";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterAll, afterEach, beforeAll, describe, expect, it, vi } from "vitest";
import type { GenerationErrorEnvelope, GenerationStage } from "../../api/ndjson";
import { PRODUCT_COPY } from "../../i18n/copy";
import type { GenerationPhase } from "../generation/useGeneration";
import { BlueprintEditorPage } from "./BlueprintEditorPage";

type UseGenerationOverride = {
  phase: GenerationPhase;
  currentStage: GenerationStage | null;
  succeededStages: GenerationStage[];
  totalStages: number | null;
  error: GenerationErrorEnvelope | null;
  begin: () => void;
  cancel: () => void;
};

const useGenerationOverride = vi.hoisted(() => ({
  current: null as UseGenerationOverride | null,
}));

vi.mock("../generation/useGeneration", async (importOriginal) => {
  const actual =
    await importOriginal<typeof import("../generation/useGeneration")>();
  return {
    ...actual,
    useGeneration: (options: Parameters<typeof actual.useGeneration>[0]) => {
      const override = useGenerationOverride.current;
      if (override) {
        return override;
      }
      return actual.useGeneration(options);
    },
  };
});

const copy = PRODUCT_COPY.zh;

const server = setupServer();

beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
afterEach(() => {
  useGenerationOverride.current = null;
  server.resetHandlers();
  vi.restoreAllMocks();
});
afterAll(() => server.close());

const provenance = {
  mode: "BLUEPRINT",
  authorityByField: {},
  visionModel: null,
  textModel: null,
  imageModel: null,
  promptVersions: {},
  generationSource: "USER_AUTHORED",
  canonicalDishSignature: null,
  cacheEligibility: false,
};

const source = { originalImageAssetId: "asset-1", contextText: null, language: "zh-CN" };

function blueprintDraft(overrides: Record<string, unknown> = {}) {
  return {
    draftId: "draft-1",
    mode: "BLUEPRINT",
    baseTemplateVersion: "blueprint-v1",
    status: "DRAFT",
    revision: 1,
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
          <Route path="/drafts/:draftId" element={<BlueprintEditorPage />} />
          <Route path="/cookbook/:dishId" element={<div>cookbook page</div>} />
          <Route path="/" element={<div>home page</div>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("blueprint editor", () => {
  it("loads a blueprint draft into an editable form and saves with expectedRevision", async () => {
    const patchSpy = vi.fn((info: { request: Request }) => {
      void info;
      return HttpResponse.json(blueprintDraft({ revision: 2 }));
    });
    server.use(
      http.get("/api/v1/drafts/:draft_id", () => HttpResponse.json(blueprintDraft())),
      http.patch("/api/v1/drafts/:draft_id", patchSpy),
    );
    renderPage();

    await screen.findByDisplayValue("南瓜汤");
    const nameInput = screen.getByLabelText(copy.displayNameLabel);
    fireEvent.change(nameInput, { target: { value: "南瓜浓汤" } });
    fireEvent.click(screen.getByRole("button", { name: copy.saveDraft }));

    await waitFor(() => expect(patchSpy).toHaveBeenCalled());
    const request = patchSpy.mock.calls[0]?.[0]?.request as Request;
    const body = (await request.clone().json()) as {
      expectedRevision: number;
      presentation: { displayName: string };
    };
    expect(body.expectedRevision).toBe(1);
    expect(body.presentation.displayName).toBe("南瓜浓汤");
  });

  it("preserves an existing buff in the PATCH body", async () => {
    const patchSpy = vi.fn((info: { request: Request }) => {
      void info;
      return HttpResponse.json(blueprintDraft({ revision: 2 }));
    });
    const withBuff = blueprintDraft({
      gameplay: {
        ...blueprintDraft().gameplay,
        buff: {
          id: "spicy",
          durationMinutes: 120,
          isDebuff: false,
          attributes: { speed: 1 },
        },
      },
    });
    server.use(
      http.get("/api/v1/drafts/:draft_id", () => HttpResponse.json(withBuff)),
      http.patch("/api/v1/drafts/:draft_id", patchSpy),
    );
    renderPage();

    await screen.findByDisplayValue("南瓜汤");
    fireEvent.click(screen.getByRole("button", { name: copy.saveDraft }));

    await waitFor(() => expect(patchSpy).toHaveBeenCalled());
    const request = patchSpy.mock.calls[0]?.[0]?.request as Request;
    const body = (await request.clone().json()) as {
      gameplay: { buff: { id: string } };
    };
    expect(body.gameplay.buff.id).toBe("spicy");
  });

  it("shows internal name and description validation without PATCH", async () => {
    const patchSpy = vi.fn((info: { request: Request }) => {
      void info;
      return HttpResponse.json(blueprintDraft({ revision: 2 }));
    });
    server.use(
      http.get("/api/v1/drafts/:draft_id", () => HttpResponse.json(blueprintDraft())),
      http.patch("/api/v1/drafts/:draft_id", patchSpy),
    );
    renderPage();

    await screen.findByDisplayValue("南瓜汤");
    fireEvent.change(screen.getByLabelText(copy.internalNameLabel), {
      target: { value: "bad-name" },
    });
    fireEvent.change(screen.getByLabelText(copy.descriptionLabel), {
      target: { value: "" },
    });
    fireEvent.click(screen.getByRole("button", { name: copy.saveDraft }));

    expect(await screen.findByText(copy.internalNameFormatError)).toBeVisible();
    expect(screen.getByText(copy.descriptionRequiredError)).toBeVisible();
    expect(patchSpy).not.toHaveBeenCalled();
  });

  it("shows a stale preview banner when PATCH returns STALE_PREVIEW", async () => {
    server.use(
      http.get("/api/v1/drafts/:draft_id", () =>
        HttpResponse.json(blueprintDraft({ status: "REVIEWABLE" })),
      ),
      http.patch("/api/v1/drafts/:draft_id", () =>
        HttpResponse.json(blueprintDraft({ status: "STALE_PREVIEW", revision: 2 })),
      ),
    );
    renderPage();

    await screen.findByDisplayValue("南瓜汤");
    fireEvent.click(screen.getByRole("button", { name: copy.saveDraft }));

    expect(await screen.findByText(copy.stalePreviewTitle)).toBeVisible();
  });

  it("shows a conflict banner on 409 and refreshes the draft", async () => {
    const getSpy = vi
      .fn()
      .mockReturnValueOnce(HttpResponse.json(blueprintDraft({ revision: 1 })))
      .mockReturnValueOnce(HttpResponse.json(blueprintDraft({ revision: 2 })));
    server.use(
      http.get("/api/v1/drafts/:draft_id", getSpy),
      http.patch("/api/v1/drafts/:draft_id", () =>
        HttpResponse.json({ error: { code: "PTS_STATE_REVISION_CONFLICT" } }, { status: 409 }),
      ),
    );
    renderPage();

    await screen.findByDisplayValue("南瓜汤");
    fireEvent.click(screen.getByRole("button", { name: copy.saveDraft }));

    expect(await screen.findByText(copy.revisionConflictTitle)).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: copy.refreshDraft }));

    expect(await screen.findByText(/版本：2/)).toBeVisible();
    expect(getSpy).toHaveBeenCalledTimes(2);
  });

  it("selects ingredients from the ingredient picker modal", async () => {
    server.use(
      http.get("/api/v1/drafts/:draft_id", () =>
        HttpResponse.json(blueprintDraft({ gameplay: null })),
      ),
      http.get("/api/v1/catalog/ingredients", () =>
        HttpResponse.json({
          catalogVersion: "stardew-1.6.15-v1",
          items: [{ itemId: "256", displayNameEn: "Tomato", displayNameZh: "西红柿" }],
          total: 1,
        }),
      ),
    );
    renderPage();

    await screen.findByText(copy.editingBlueprint);
    fireEvent.click(screen.getByRole("button", { name: copy.pickIngredient }));
    fireEvent.click(await screen.findByRole("button", { name: /西红柿/ }));

    expect(await screen.findByText(/西红柿（256）/)).toBeVisible();
  });

  it("picks a category and tags from their picker modals", async () => {
    server.use(
      http.get("/api/v1/drafts/:draft_id", () => HttpResponse.json(blueprintDraft())),
      http.get("/api/v1/meta/categories", () =>
        HttpResponse.json({
          items: [{ value: "主菜" }, { value: "汤类" }],
          nextCursor: null,
          total: 2,
        }),
      ),
      http.get("/api/v1/meta/tags", () =>
        HttpResponse.json({
          items: [{ value: "家常" }, { value: "清淡" }],
          nextCursor: null,
          total: 2,
        }),
      ),
    );
    renderPage();

    await screen.findByDisplayValue("南瓜汤");
    fireEvent.click(screen.getByRole("button", { name: copy.pickCategory }));
    fireEvent.click(await screen.findByRole("button", { name: "主菜" }));
    expect(screen.getByText("主菜")).toBeVisible();

    fireEvent.click(screen.getByRole("button", { name: copy.pickTags }));
    fireEvent.click(await screen.findByRole("button", { name: "家常" }));
    expect(await screen.findByText("家常")).toBeVisible();
  });

  it("shows an update preview action when STALE_PREVIEW and blocks accept", async () => {
    server.use(
      http.get("/api/v1/drafts/:draft_id", () =>
        HttpResponse.json(blueprintDraft({ status: "STALE_PREVIEW", revision: 2 })),
      ),
    );
    renderPage();

    await screen.findByText(copy.editingBlueprint);
    expect(screen.getByRole("button", { name: copy.updatePreview })).toBeVisible();
    expect(screen.queryByRole("button", { name: copy.archiveDish })).toBeNull();
  });

  it("shows a generate preview action for DRAFT and completes first generation", async () => {
    const getSpy = vi
      .fn()
      .mockReturnValueOnce(
        HttpResponse.json(blueprintDraft({ status: "DRAFT", revision: 1 })),
      )
      .mockReturnValueOnce(
        HttpResponse.json(blueprintDraft({ status: "REVIEWABLE", revision: 2 })),
      );
    server.use(
      http.get("/api/v1/drafts/:draft_id", getSpy),
      http.post("/api/v1/drafts/:draft_id/generate", () =>
        new Response(
          '{"type":"attempt.started","attemptId":"a-1"}\n{"type":"stage.started","stage":"INPUT_VALIDATION","ordinal":1,"total":6}\n{"type":"attempt.succeeded","attemptId":"a-1","draftRevision":2,"draft":{}}\n',
          { status: 200, headers: { "Content-Type": "application/x-ndjson" } },
        ),
      ),
    );
    renderPage();

    await screen.findByText(copy.editingBlueprint);
    expect(screen.getByRole("button", { name: copy.generatePreview })).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: copy.generatePreview }));

    expect(await screen.findByRole("button", { name: copy.archiveDish })).toBeVisible();
    expect(getSpy).toHaveBeenCalledTimes(2);
  });

  it("shows a generate preview action for READY drafts", async () => {
    server.use(
      http.get("/api/v1/drafts/:draft_id", () =>
        HttpResponse.json(blueprintDraft({ status: "READY", revision: 1 })),
      ),
    );
    renderPage();

    await screen.findByText(copy.editingBlueprint);
    expect(screen.getByRole("button", { name: copy.generatePreview })).toBeVisible();
  });

  it("updates preview from STALE_PREVIEW and returns to REVIEWABLE", async () => {
    const getSpy = vi
      .fn()
      .mockReturnValueOnce(
        HttpResponse.json(blueprintDraft({ status: "STALE_PREVIEW", revision: 2 })),
      )
      .mockReturnValueOnce(
        HttpResponse.json(blueprintDraft({ status: "REVIEWABLE", revision: 3 })),
      );
    server.use(
      http.get("/api/v1/drafts/:draft_id", getSpy),
      http.post("/api/v1/drafts/:draft_id/generate", () =>
        new Response(
          '{"type":"attempt.started","attemptId":"a-1"}\n{"type":"stage.started","stage":"INPUT_VALIDATION","ordinal":1,"total":6}\n{"type":"attempt.succeeded","attemptId":"a-1","draftRevision":3,"draft":{}}\n',
          { status: 200, headers: { "Content-Type": "application/x-ndjson" } },
        ),
      ),
    );
    renderPage();

    await screen.findByText(copy.editingBlueprint);
    fireEvent.click(screen.getByRole("button", { name: copy.updatePreview }));

    expect(await screen.findByRole("button", { name: copy.archiveDish })).toBeVisible();
    expect(getSpy).toHaveBeenCalledTimes(2);
  });

  it("keeps STALE_PREVIEW when update preview fails", async () => {
    server.use(
      http.get("/api/v1/drafts/:draft_id", () =>
        HttpResponse.json(blueprintDraft({ status: "STALE_PREVIEW", revision: 2 })),
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

    await screen.findByText(copy.editingBlueprint);
    fireEvent.click(screen.getByRole("button", { name: copy.updatePreview }));

    expect(await screen.findByText("生成结果未通过校验。")).toBeVisible();
    expect(screen.getByRole("button", { name: copy.updatePreview })).toBeVisible();
    expect(screen.queryByRole("button", { name: copy.archiveDish })).toBeNull();
  });

  it("cancels an update preview and stays recoverable", async () => {
    const cancelSpy = vi.fn(() => new Response(null, { status: 202 }));
    server.use(
      http.get("/api/v1/drafts/:draft_id", () =>
        HttpResponse.json(blueprintDraft({ status: "STALE_PREVIEW", revision: 2 })),
      ),
      http.post("/api/v1/drafts/:draft_id/generate", () =>
        new Response('{"type":"attempt.started","attemptId":"a-1"}\n', {
          status: 200,
          headers: { "Content-Type": "application/x-ndjson" },
        }),
      ),
      http.post("/api/v1/drafts/:draft_id/cancel", cancelSpy),
    );
    renderPage();

    await screen.findByText(copy.editingBlueprint);
    fireEvent.click(screen.getByRole("button", { name: copy.updatePreview }));

    fireEvent.click(screen.getByRole("button", { name: copy.cancelGeneration }));

    expect(await screen.findByText(copy.generationCancelled)).toBeVisible();
    expect(cancelSpy).toHaveBeenCalledTimes(1);
    expect(screen.getByRole("button", { name: copy.updatePreview })).toBeVisible();
  });

  it("offers a retry generation entry for a FAILED draft", async () => {
    server.use(
      http.get("/api/v1/drafts/:draft_id", () =>
        HttpResponse.json(blueprintDraft({ status: "FAILED", revision: 1 })),
      ),
    );
    renderPage();

    await screen.findByText(copy.editingBlueprint);
    expect(screen.getByRole("button", { name: copy.retryGeneration })).toBeVisible();
  });

  it("retries a FAILED draft back to REVIEWABLE", async () => {
    const getSpy = vi
      .fn()
      .mockReturnValueOnce(
        HttpResponse.json(blueprintDraft({ status: "FAILED", revision: 1 })),
      )
      .mockReturnValueOnce(
        HttpResponse.json(blueprintDraft({ status: "REVIEWABLE", revision: 2 })),
      );
    server.use(
      http.get("/api/v1/drafts/:draft_id", getSpy),
      http.post("/api/v1/drafts/:draft_id/generate", () =>
        new Response(
          '{"type":"attempt.started","attemptId":"a-1"}\n{"type":"stage.started","stage":"INPUT_VALIDATION","ordinal":1,"total":6}\n{"type":"attempt.succeeded","attemptId":"a-1","draftRevision":2,"draft":{}}\n',
          { status: 200, headers: { "Content-Type": "application/x-ndjson" } },
        ),
      ),
    );
    renderPage();

    await screen.findByText(copy.editingBlueprint);
    fireEvent.click(screen.getByRole("button", { name: copy.retryGeneration }));

    expect(await screen.findByRole("button", { name: copy.archiveDish })).toBeVisible();
    expect(getSpy).toHaveBeenCalledTimes(2);
  });

  it("discards the draft after confirmation and navigates home", async () => {
    const confirmSpy = vi.spyOn(window, "confirm").mockReturnValue(true);
    const discardSpy = vi.fn(() => new Response(null, { status: 204 }));
    server.use(
      http.get("/api/v1/drafts/:draft_id", () =>
        HttpResponse.json(blueprintDraft({ status: "DRAFT", revision: 1 })),
      ),
      http.post("/api/v1/drafts/:draft_id/discard", discardSpy),
    );
    renderPage();

    fireEvent.click(await screen.findByRole("button", { name: copy.discardDraft }));

    expect(confirmSpy).toHaveBeenCalledWith(copy.discardDraftConfirm);
    await waitFor(() => expect(discardSpy).toHaveBeenCalledTimes(1));
    expect(await screen.findByText("home page")).toBeVisible();
  });

  it("does not discard when confirmation is cancelled", async () => {
    const confirmSpy = vi.spyOn(window, "confirm").mockReturnValue(false);
    const discardSpy = vi.fn(() => new Response(null, { status: 204 }));
    server.use(
      http.get("/api/v1/drafts/:draft_id", () =>
        HttpResponse.json(blueprintDraft({ status: "DRAFT", revision: 1 })),
      ),
      http.post("/api/v1/drafts/:draft_id/discard", discardSpy),
    );
    renderPage();

    fireEvent.click(await screen.findByRole("button", { name: copy.discardDraft }));

    expect(confirmSpy).toHaveBeenCalledWith(copy.discardDraftConfirm);
    expect(discardSpy).not.toHaveBeenCalled();
    expect(screen.queryByText("home page")).toBeNull();
  });

  it("does not expose a retry entry for a REVIEWABLE blueprint on generation error", async () => {
    // The backend has no generation action for a REVIEWABLE blueprint (it must
    // first be edited into STALE_PREVIEW), so a GenerationError must not offer
    // a retry button that would 409.
    useGenerationOverride.current = {
      phase: "error",
      currentStage: null,
      succeededStages: [],
      totalStages: null,
      error: {
        code: "PTS_GEN_VALIDATION_FAILED",
        message: "生成结果未通过校验。",
        retryable: false,
        requestId: "req-1",
        recommendedAction: "",
      },
      begin: vi.fn(),
      cancel: vi.fn(),
    };
    server.use(
      http.get("/api/v1/drafts/:draft_id", () =>
        HttpResponse.json(blueprintDraft({ status: "REVIEWABLE", revision: 2 })),
      ),
    );
    renderPage();

    await screen.findByText(copy.editingBlueprint);
    expect(screen.getByText("生成结果未通过校验。")).toBeVisible();
    expect(screen.queryByRole("button", { name: copy.retryGeneration })).toBeNull();
  });
});
