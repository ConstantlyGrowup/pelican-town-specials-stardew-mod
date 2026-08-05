import "@testing-library/jest-dom/vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { setupServer } from "msw/node";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import {
  afterAll,
  afterEach,
  beforeAll,
  beforeEach,
  describe,
  expect,
  it,
  vi,
} from "vitest";
import { PRODUCT_COPY } from "../../i18n/copy";
import { resetSelectionStore, toggleSelection } from "../cookbook/selectionStore";
import { PackMenuPage } from "./PackMenuPage";

const copy = PRODUCT_COPY.zh;

const server = setupServer();

beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
afterEach(() => server.resetHandlers());
beforeEach(() => resetSelectionStore());
afterAll(() => server.close());

const dish = {
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
    recovery: {
      edibility: 20,
      energyRestore: 50,
      healthRestore: 22,
      calculationVersion: "stardew-1.6",
    },
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

function exportRecord() {
  return {
    exportId: "export-1",
    spec: {
      dishIds: ["dish-1"],
      packDisplayName: "家庭菜单",
      packSlug: "FamilyMenu",
      version: "1.0.0",
      description: "一份装满鹈鹕镇风味的菜单。",
      language: "zh-CN",
    },
    authorName: "D20260801",
    uniqueId: "D20260801.PelicanTownSpecials.FamilyMenu",
    status: "SUCCEEDED",
    dishContentHashes: { "dish-1": "a".repeat(64) },
    compilerVersion: "task16-export-compiler-v1",
    gameVersion: "1.6.15",
    contentPatcherFormat: "2.9.0",
    validation: {
      valid: true,
      issues: [],
      validatedAt: "2026-08-04T00:00:00Z",
      validatorVersion: "task16-export-validator-v1",
    },
    artifactAssetId: "00000000-0000-4000-8000-000000000004",
    createdAt: "2026-08-04T00:00:00Z",
    finishedAt: "2026-08-04T00:00:01Z",
    error: null,
  };
}

function renderPackMenuWithIssue(issue: {
  code: string;
  severity: "ERROR" | "WARNING";
}) {
  server.use(
    http.get("/api/v1/cookbook/:dish_id", () => HttpResponse.json(dish)),
    http.post("/api/v1/exports/validate", () =>
      HttpResponse.json({
        valid: issue.severity !== "ERROR",
        issues: [issue],
        validatedAt: "2026-08-04T00:00:00Z",
        validatorVersion: "task16-export-validator-v1",
      }),
    ),
  );
  toggleSelection("dish-1");
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={["/pack-menu"]}>
        <Routes>
          <Route path="/pack-menu" element={<PackMenuPage />} />
          <Route
            path="/bring-in-game/:exportId"
            element={<div>bring-in-game</div>}
          />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

async function clickValidate() {
  fireEvent.click(screen.getByRole("button", { name: copy.validateButton }));
}

describe("pack menu", () => {
  it("renders selected dishes and validates the pack", async () => {
    renderPackMenuWithIssue({
      code: "PTS_VALIDATION_INGREDIENT_ID_UNKNOWN",
      severity: "ERROR",
    });

    expect(await screen.findByRole("heading", { name: copy.packMenuTitle })).toBeVisible();
    expect(await screen.findByText("春日面碗")).toBeVisible();
    expect(screen.getByLabelText(copy.packSlugLabel)).toHaveValue("FamilyMenu");
  });

  it("blocks packaging when validation has errors", async () => {
    renderPackMenuWithIssue({
      code: "PTS_VALIDATION_INGREDIENT_ID_UNKNOWN",
      severity: "ERROR",
    });

    await screen.findByText("春日面碗");
    await clickValidate();

    expect(await screen.findByText(/原料/)).toBeVisible();
    expect(screen.getByText(copy.validationHasErrors)).toBeVisible();
    expect(screen.getByRole("button", { name: copy.packButton })).toBeDisabled();
  });

  it("requires explicit confirmation for warnings before packaging", async () => {
    renderPackMenuWithIssue({
      code: "PTS_VALIDATION_GAMEPLAY_EDIBILITY_OUTSIDE_OBSERVED_RANGE",
      severity: "WARNING",
    });

    await screen.findByText("春日面碗");
    await clickValidate();

    expect(await screen.findByText(copy.validationHasWarnings)).toBeVisible();
    expect(screen.getByRole("button", { name: copy.packButton })).toBeDisabled();

    fireEvent.click(screen.getByRole("checkbox"));
    expect(screen.getByRole("button", { name: copy.packButton })).toBeEnabled();
  });

  it("packs a valid menu and navigates to bring-it-in-game", async () => {
    const packSpy = vi.fn();
    server.use(
      http.get("/api/v1/cookbook/:dish_id", () => HttpResponse.json(dish)),
      http.post("/api/v1/exports/validate", () =>
        HttpResponse.json({
          valid: true,
          issues: [],
          validatedAt: "2026-08-04T00:00:00Z",
          validatorVersion: "task16-export-validator-v1",
        }),
      ),
      http.post("/api/v1/exports", (info) => {
        packSpy(info);
        return HttpResponse.json(exportRecord(), { status: 201 });
      }),
    );
    toggleSelection("dish-1");
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter initialEntries={["/pack-menu"]}>
          <Routes>
            <Route path="/pack-menu" element={<PackMenuPage />} />
            <Route
              path="/bring-in-game/:exportId"
              element={<div>bring-in-game</div>}
            />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>,
    );

    await screen.findByText("春日面碗");
    await clickValidate();
    await screen.findByText(copy.validationPassed);

    fireEvent.click(screen.getByRole("button", { name: copy.packButton }));

    expect(await screen.findByText("bring-in-game")).toBeVisible();
    expect(packSpy).toHaveBeenCalledTimes(1);
    const captured = packSpy.mock.calls[0][0] as { request: Request };
    expect(captured.request.headers.get("Idempotency-Key")).toBeTruthy();
  });
});
