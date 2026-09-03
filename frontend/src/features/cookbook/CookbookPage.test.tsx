import "@testing-library/jest-dom/vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { setupServer } from "msw/node";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterAll, afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import { waitFor } from "@testing-library/react";
import { catalogs } from "../../i18n/copy";
import { CookbookDetailPage } from "./CookbookDetailPage";
import { CookbookPage } from "./CookbookPage";
import { getSelectedDishIds, resetSelectionStore } from "./selectionStore";

const copy = catalogs["zh-CN"];

const server = setupServer();

beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
afterEach(() => server.resetHandlers());
beforeEach(() => {
  resetSelectionStore();
  server.use(
    http.get("/api/v1/cookbook/:dish_id", () => HttpResponse.json(detail)),
  );
});
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

const secondSummary = {
  ...summary,
  dishId: "dish-2",
  displayName: "菠菜烟熏三文鱼",
  description: "烟熏香气和春日蔬菜的组合。",
};

const secondDetail = {
  ...detail,
  ...secondSummary,
  internalName: "SmokedSpinachSalmon",
  visuals: {
    ...detail.visuals,
    previewAssetId: "00000000-0000-4000-8000-000000000012",
    icon16AssetId: "00000000-0000-4000-8000-000000000013",
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

  it("uses the collection tab icon without implying a recipe capacity", async () => {
    const { container } = renderInRouter(["/cookbook"]);

    expect(await screen.findByRole("heading", { name: copy.cookbookTitle })).toBeVisible();
    expect(container.querySelector(".cookbook-heading .game-ui-icon--collections")).not.toBeNull();
    expect(screen.queryByText(/\/\s*24/)).not.toBeInTheDocument();
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

  it("switches the right preview without navigating, then opens the full detail page", async () => {
    server.use(
      http.get("/api/v1/cookbook", () =>
        HttpResponse.json({ items: [summary, secondSummary], nextCursor: null, total: 2 }),
      ),
      http.get("/api/v1/cookbook/:dish_id", ({ params }) =>
        HttpResponse.json(params.dish_id === "dish-2" ? secondDetail : detail),
      ),
    );
    renderInRouter(["/cookbook"]);

    expect(await screen.findByRole("img", { name: "春日面碗预览" })).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: "查看菠菜烟熏三文鱼预览" }));

    expect(await screen.findByRole("img", { name: "菠菜烟熏三文鱼预览" })).toHaveAttribute(
      "src",
      "/api/v1/assets/00000000-0000-4000-8000-000000000012",
    );
    expect(screen.getByRole("link", { name: "查看完整菜品 →" })).toHaveAttribute(
      "href",
      "/cookbook/dish-2",
    );
  });

  it("renders detail without source fields", async () => {
    server.use(
      http.get("/api/v1/cookbook/:dish_id", () =>
        HttpResponse.json({ ...detail, internalProvenance: { secret: true } }),
      ),
    );
    const { container } = renderInRouter(["/cookbook/dish-1"]);

    expect(await screen.findByRole("heading", { name: "春日面碗" })).toBeVisible();
    expect(screen.getByText("Parsnip × 1")).toBeVisible();
    expect(screen.getByRole("img", { name: "春日面碗预览" })).toHaveAttribute(
      "src",
      "/api/v1/assets/00000000-0000-4000-8000-000000000002",
    );
    expect(screen.getByRole("img", { name: "春日面碗像素图标" })).toHaveAttribute(
      "src",
      "/api/v1/assets/00000000-0000-4000-8000-000000000003",
    );
    const statRows = [...container.querySelectorAll(".stat-row")];
    expect(statRows[0]?.querySelector(".game-ui-icon--energy")).not.toBeNull();
    expect(statRows[2]?.querySelector(".specific-icon--edibility")).not.toBeNull();
    expect(screen.queryByText(/internalProvenance|secret/)).not.toBeInTheDocument();
  });

  it("shows parallel pack-menu and batch-delete actions only after selection", async () => {
    server.use(
      http.get("/api/v1/cookbook", () =>
        HttpResponse.json({ items: [summary, secondSummary], nextCursor: null, total: 2 }),
      ),
    );
    renderInRouter(["/cookbook"]);

    await screen.findByRole("heading", { name: "春日面碗" });
    expect(screen.queryByRole("button", { name: copy.batchDelete })).toBeNull();

    fireEvent.click(screen.getAllByRole("checkbox")[0]);
    const batchDelete = screen.getByRole("button", { name: copy.batchDelete });
    expect(batchDelete).toBeVisible();
    expect(screen.getByRole("button", { name: copy.packMenu })).toBeVisible();
  });

  it("confirms batch delete, deletes each selected dish, and clears the selection", async () => {
    const deleted: string[] = [];
    server.use(
      http.get("/api/v1/cookbook", () =>
        HttpResponse.json({ items: [summary, secondSummary], nextCursor: null, total: 2 }),
      ),
      http.delete("/api/v1/cookbook/:dish_id", ({ params }) => {
        deleted.push(String(params.dish_id));
        return new HttpResponse(null, { status: 204 });
      }),
    );
    renderInRouter(["/cookbook"]);

    await screen.findByRole("heading", { name: "春日面碗" });
    fireEvent.click(screen.getAllByRole("checkbox")[0]);
    fireEvent.click(screen.getAllByRole("checkbox")[1]);
    fireEvent.click(screen.getByRole("button", { name: copy.batchDelete }));

    expect(
      screen.getByText(copy.batchDeleteMessage.replace("{count}", "2")),
    ).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: copy.deleteDish }));

    await waitFor(() => expect(deleted.sort()).toEqual(["dish-1", "dish-2"]));
    await waitFor(() => expect(getSelectedDishIds().size).toBe(0));
    expect(screen.queryByText(copy.batchDeleteMessage.replace("{count}", "2"))).toBeNull();
  });

  it("keeps the selection and shows an error when a batch delete fails", async () => {
    server.use(
      http.get("/api/v1/cookbook", () =>
        HttpResponse.json({ items: [summary], nextCursor: null, total: 1 }),
      ),
      http.delete("/api/v1/cookbook/:dish_id", () =>
        HttpResponse.json({ detail: "boom" }, { status: 500 }),
      ),
    );
    renderInRouter(["/cookbook"]);

    await screen.findByRole("heading", { name: "春日面碗" });
    fireEvent.click(screen.getAllByRole("checkbox")[0]);
    fireEvent.click(screen.getByRole("button", { name: copy.batchDelete }));
    fireEvent.click(screen.getByRole("button", { name: copy.deleteDish }));

    expect(await screen.findByRole("alert")).toHaveTextContent(copy.batchDeleteFailed);
    expect(getSelectedDishIds()).toEqual(new Set(["dish-1"]));
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
