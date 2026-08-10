import "@testing-library/jest-dom/vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { setupServer } from "msw/node";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import {
  afterAll,
  afterEach,
  beforeAll,
  describe,
  expect,
  it,
  vi,
} from "vitest";
import { catalogs } from "../../i18n/copy";
import { BringInGamePage } from "./BringInGamePage";

const copy = catalogs["zh-CN"];

const server = setupServer();

beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

const record = {
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

function renderInRouter() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={["/bring-in-game/export-1"]}>
        <Routes>
          <Route path="/bring-in-game/:exportId" element={<BringInGamePage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("bring it in-game", () => {
  it("shows the export record, download link and fixed install steps", async () => {
    server.use(
      http.get("/api/v1/exports/:export_id", () => HttpResponse.json(record)),
    );
    renderInRouter();

    expect(await screen.findByText("家庭菜单")).toBeVisible();
    expect(screen.getByText(/版本: 1\.0\.0/)).toBeVisible();
    expect(screen.getByText(copy.bringInGameStep1Title)).toBeVisible();
    expect(screen.getByText(copy.bringInGameStep1Text)).toBeVisible();
    expect(screen.getByText(copy.bringInGameStep4Text)).toBeVisible();
    expect(screen.getByRole("button", { name: copy.downloadZip })).toBeVisible();
  });

  it("calls open-folder endpoint", async () => {
    const openFolderSpy = vi.fn(() => new HttpResponse(null, { status: 204 }));
    server.use(
      http.get("/api/v1/exports/:export_id", () => HttpResponse.json(record)),
      http.post("/api/v1/exports/:export_id/open-folder", openFolderSpy),
    );
    renderInRouter();

    await screen.findByRole("button", { name: copy.openExportFolder });
    fireEvent.click(screen.getByRole("button", { name: copy.openExportFolder }));

    await waitFor(() => expect(openFolderSpy).toHaveBeenCalledTimes(1));
  });
});
