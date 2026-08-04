import "@testing-library/jest-dom/vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { setupServer } from "msw/node";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterAll, afterEach, beforeAll, describe, expect, it, vi } from "vitest";
import { PRODUCT_COPY } from "../../i18n/copy";
import { BlueprintEditorPage } from "./BlueprintEditorPage";

const copy = PRODUCT_COPY.zh;

const server = setupServer();

beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
afterEach(() => server.resetHandlers());
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

function askGusDraft() {
  return blueprintDraft({
    mode: "ASK_GUS",
    baseTemplateVersion: null,
    provenance: { ...provenance, mode: "ASK_GUS", visionModel: "vision-model", cacheEligibility: true },
  });
}

function renderPage() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={["/drafts/draft-1"]}>
        <Routes>
          <Route path="/drafts/:draftId" element={<BlueprintEditorPage />} />
          <Route path="/cookbook/:dishId" element={<div>cookbook page</div>} />
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

  it("selects ingredients from the catalog search", async () => {
    server.use(
      http.get("/api/v1/drafts/:draft_id", () =>
        HttpResponse.json(blueprintDraft({ gameplay: null })),
      ),
      http.get("/api/v1/catalog/ingredients", () =>
        HttpResponse.json({
          catalogVersion: "stardew-1.6.15-v1",
          items: [{ itemId: "256", displayNameEn: "Tomato", displayNameZh: "西红柿" }],
        }),
      ),
    );
    renderPage();

    await screen.findByText(copy.editingBlueprint);
    fireEvent.change(screen.getByRole("textbox", { name: copy.ingredientSearchPlaceholder }), {
      target: { value: "tomat" },
    });
    fireEvent.click(screen.getByRole("button", { name: copy.ingredientSearchPlaceholder }));
    fireEvent.click(await screen.findByRole("button", { name: copy.addIngredient }));

    expect(await screen.findByText(/西红柿（256）/)).toBeVisible();
  });

  it("shows ask gus as read-only with a convert action", async () => {
    const convertSpy = vi.fn(() =>
      HttpResponse.json(blueprintDraft({ draftId: "draft-2" })),
    );
    server.use(
      http.get("/api/v1/drafts/:draft_id", () => HttpResponse.json(askGusDraft())),
      http.post("/api/v1/drafts/:draft_id/convert-to-blueprint", convertSpy),
    );
    renderPage();

    expect(await screen.findByText(copy.readOnlyAskGus)).toBeVisible();
    expect(screen.queryByText(copy.saveDraft)).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: copy.convertToBlueprint }));

    await waitFor(() => expect(convertSpy).toHaveBeenCalledTimes(1));
  });
});
