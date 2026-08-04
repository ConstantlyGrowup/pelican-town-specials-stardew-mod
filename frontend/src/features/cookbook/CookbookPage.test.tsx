import "@testing-library/jest-dom/vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { setupServer } from "msw/node";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterAll, afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import { PRODUCT_COPY } from "../../i18n/copy";
import { CookbookDetailPage } from "./CookbookDetailPage";
import { CookbookPage } from "./CookbookPage";
import { getSelectedDishIds, resetSelectionStore } from "./selectionStore";

const copy = PRODUCT_COPY.zh;

const server = setupServer();

beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
afterEach(() => server.resetHandlers());
beforeEach(() => resetSelectionStore());
afterAll(() => server.close());

function renderInRouter(initialEntries: string[]) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={initialEntries}>
        <Routes>
          <Route path="/cookbook" element={<CookbookPage />} />
          <Route path="/cookbook/:dishId" element={<CookbookDetailPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

const summary = {
  dishId: "dish-1",
  archivedAt: "2026-08-04T00:00:00Z",
  displayName: "春日面碗",
  categoryLabel: "主菜",
  description: "一碗春天气息的热汤面。",
  tags: ["spring", "noodles"],
};

const detail = {
  dishId: "dish-1",
  archivedAt: "2026-08-04T00:00:00Z",
  displayName: "春日面碗",
  internalName: "SpringNoodleBowl",
  categoryLabel: "主菜",
  description: "一碗春天气息的热汤面。",
  tags: ["spring", "noodles"],
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
    recovery: { edibility: 20, energyRestore: 50, healthRestore: 22, calculationVersion: "stardew-1.6" },
    sellPrice: 35,
    isDrink: false,
    recipeUnlock: "DEFAULT",
  },
  visuals: {
    generatedArtAssetId: "00000000-0000-4000-8000-000000000001",
    previewAssetId: "00000000-0000-4000-8000-000000000002",
    iconSourceAssetId: null,
    icon16AssetId: "00000000-0000-4000-8000-000000000003",
    sourceRevision: 1,
    promptVersion: "visual-v1",
  },
};

describe("cookbook", () => {
  it("renders summaries and never shows source labels even when injected", async () => {
    server.use(
      http.get("/api/v1/cookbook", () =>
        HttpResponse.json({
          items: [
            {
              ...summary,
              mode: "ASK_GUS",
              sourceDraftId: "draft-secret",
              gusComment: "gus-secret",
              visionModel: "model-secret",
            },
          ],
          nextCursor: null,
          total: 1,
        }),
      ),
    );
    renderInRouter(["/cookbook"]);

    expect(await screen.findByRole("heading", { name: "春日面碗" })).toBeVisible();
    expect(screen.getByText("主菜")).toBeVisible();
    expect(screen.queryByText(/ASK_GUS|Gus|model-secret/)).not.toBeInTheDocument();
  });

  it("toggles selection by dishId only", async () => {
    server.use(
      http.get("/api/v1/cookbook", () =>
        HttpResponse.json({ items: [summary], nextCursor: null, total: 1 }),
      ),
    );
    renderInRouter(["/cookbook"]);

    await screen.findByRole("heading", { name: "春日面碗" });
    fireEvent.click(screen.getByRole("checkbox"));

    expect(getSelectedDishIds()).toEqual(new Set(["dish-1"]));
  });

  it("renders detail without source fields", async () => {
    server.use(
      http.get("/api/v1/cookbook/:dish_id", () =>
        HttpResponse.json({ ...detail, internalProvenance: { secret: true } }),
      ),
    );
    renderInRouter(["/cookbook/dish-1"]);

    expect(await screen.findByRole("heading", { name: "春日面碗" })).toBeVisible();
    expect(screen.getByText("Parsnip × 1")).toBeVisible();
    expect(screen.queryByText(/internalProvenance|secret/)).not.toBeInTheDocument();
  });

  it("confirms before delete, calls DELETE, and navigates back", async () => {
    const deleteSpy = vi.fn(() => new HttpResponse(null, { status: 204 }));
    server.use(
      http.get("/api/v1/cookbook/:dish_id", () => HttpResponse.json(detail)),
      http.delete("/api/v1/cookbook/:dish_id", deleteSpy),
    );
    renderInRouter(["/cookbook/dish-1"]);

    await screen.findByRole("heading", { name: "春日面碗" });
    fireEvent.click(screen.getByRole("button", { name: copy.deleteDish }));
    fireEvent.click(screen.getByRole("button", { name: copy.cancelDelete }));
    expect(deleteSpy).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole("button", { name: copy.deleteDish }));
    fireEvent.click(screen.getByRole("button", { name: copy.confirmDelete }));

    expect(await screen.findByText(copy.cookbookTitle)).toBeVisible();
    expect(deleteSpy).toHaveBeenCalledTimes(1);
    expect(getSelectedDishIds().has("dish-1")).toBe(false);
  });
});
