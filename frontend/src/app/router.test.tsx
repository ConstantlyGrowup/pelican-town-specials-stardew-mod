import "@testing-library/jest-dom/vitest";
import { render, screen, within } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { setupServer } from "msw/node";
import { MemoryRouter } from "react-router-dom";
import { afterAll, afterEach, beforeAll, describe, expect, it } from "vitest";
import { catalogs } from "../i18n/copy";
import { AppProviders } from "./providers";
import { AppRouter } from "./router";

const copy = catalogs["zh-CN"];

const server = setupServer(
  http.get("/api/v1/settings/provider", () =>
    HttpResponse.json({
      providerKind: "OPENAI_COMPATIBLE",
      baseUrl: "https://yibuapi.com/v1",
      visionModel: "",
      textModel: "",
      imageModel: "",
      chatTimeoutSeconds: 120,
      imageTimeoutSeconds: 300,
      maxAutomaticRetries: 2,
      apiKeyConfigured: false,
      apiKeySource: "NONE",
    }),
  ),
  http.get("/api/v1/cookbook", () =>
    HttpResponse.json({ items: [], nextCursor: null, total: 0 }),
  ),
  http.get("/api/v1/drafts", () =>
    HttpResponse.json({
      items: [
        {
          draftId: "draft-1",
          mode: "BLUEPRINT",
          status: "DRAFT",
          revision: 1,
          updatedAt: "2026-08-04T00:00:00Z",
          displayName: "南瓜汤",
          originalImageAssetId: "asset-1",
        },
        {
          draftId: "draft-2",
          mode: "ASK_GUS",
          status: "REVIEWABLE",
          revision: 3,
          updatedAt: "2026-08-03T00:00:00Z",
          displayName: "",
          originalImageAssetId: "asset-2",
        },
      ],
      nextCursor: null,
      total: 2,
    }),
  ),
  http.get("/api/v1/drafts/:draft_id", () =>
    HttpResponse.json({
      draftId: "draft-1",
      mode: "BLUEPRINT",
      baseTemplateVersion: "blueprint-v1",
      status: "DRAFT",
      revision: 1,
      source: { originalImageAssetId: "asset-1", contextText: null, language: "zh-CN" },
      analysis: null,
      presentation: null,
      gameplay: null,
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
    }),
  ),
);

beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

function renderAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <AppProviders>
        <AppRouter />
      </AppProviders>
    </MemoryRouter>,
  );
}

describe("router", () => {
  it("resolves the home page with frozen product copy and a draft list", async () => {
    renderAt("/");
    expect(screen.getByRole("link", { name: copy.home })).toHaveAttribute(
      "href",
      "/",
    );
    expect(screen.getByRole("heading", { name: copy.createFirstDraft })).toBeVisible();
    expect(screen.getByText(copy.tagline)).toBeVisible();
    expect(await screen.findByRole("heading", { name: "南瓜汤" })).toBeVisible();
    expect(screen.getByRole("link", { name: "南瓜汤" })).toHaveAttribute(
      "href",
      "/drafts/draft-1",
    );
    expect(screen.getByText(copy.unnamedDraft)).toBeVisible();
    expect(screen.getByText(copy.draftStatusLabels.REVIEWABLE)).toBeVisible();
  });

  it("resolves the home page empty state when there are no drafts", async () => {
    server.use(
      http.get("/api/v1/drafts", () =>
        HttpResponse.json({ items: [], nextCursor: null, total: 0 }),
      ),
    );
    renderAt("/");
    expect(screen.getByRole("heading", { name: copy.createFirstDraft })).toBeVisible();
    expect(await screen.findByText(copy.draftsEmpty)).toBeVisible();
    const emptyState = screen.getByText(copy.draftsEmpty).closest(".empty-state");
    expect(emptyState).not.toBeNull();
    expect(within(emptyState as HTMLElement).getByRole("link", { name: copy.createFirstDraft })).toHaveAttribute(
      "href",
      "/create",
    );
  });

  it("resolves /settings", () => {
    renderAt("/settings");
    expect(screen.getByRole("heading", { name: copy.settingsTitle })).toBeVisible();
  });

  it("resolves /create", () => {
    renderAt("/create");
    expect(screen.getByRole("heading", { name: copy.createTitle })).toBeVisible();
  });

  it("resolves /drafts/:draftId", async () => {
    renderAt("/drafts/draft-1");
    expect(
      await screen.findByRole("heading", { name: copy.editingBlueprint }),
    ).toBeVisible();
  });

  it("resolves /cookbook", () => {
    renderAt("/cookbook");
    expect(screen.getByRole("heading", { name: copy.cookbookTitle })).toBeVisible();
  });

  it("renders an in-app 404 for unknown paths", () => {
    renderAt("/definitely-not-a-page");
    expect(screen.getByRole("heading", { name: copy.notFoundTitle })).toBeVisible();
  });
});
