import "@testing-library/jest-dom/vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { setupServer } from "msw/node";
import { MemoryRouter } from "react-router-dom";
import { afterAll, afterEach, beforeAll, describe, expect, it } from "vitest";
import { PRODUCT_COPY } from "../../i18n/copy";
import { HomePage } from "./HomePage";

const copy = PRODUCT_COPY.zh;

const server = setupServer(
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
);

beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

function renderPage() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={["/"]}>
        <HomePage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("home page draft dashboard", () => {
  it("renders the product identity and a list of drafts with links", async () => {
    renderPage();

    expect(screen.getByRole("heading", { name: copy.productName })).toBeVisible();
    expect(screen.getByText(copy.tagline)).toBeVisible();
    expect(screen.getByRole("heading", { name: copy.myDrafts })).toBeVisible();

    expect(await screen.findByRole("heading", { name: "南瓜汤" })).toBeVisible();
    expect(screen.getByRole("link", { name: "南瓜汤" })).toHaveAttribute(
      "href",
      "/drafts/draft-1",
    );
    expect(screen.getByText(copy.draftStatusLabels.DRAFT)).toBeVisible();

    expect(screen.getByText(copy.unnamedDraft)).toBeVisible();
    expect(screen.getByRole("link", { name: copy.unnamedDraft })).toHaveAttribute(
      "href",
      "/drafts/draft-2",
    );
    expect(screen.getByText(copy.draftStatusLabels.REVIEWABLE)).toBeVisible();
  });

  it("renders an empty state that guides to /create", async () => {
    server.use(
      http.get("/api/v1/drafts", () =>
        HttpResponse.json({ items: [], nextCursor: null, total: 0 }),
      ),
    );
    renderPage();

    expect(await screen.findByText(copy.draftsEmpty)).toBeVisible();
    expect(screen.getByRole("link", { name: copy.createFirstDraft })).toHaveAttribute(
      "href",
      "/create",
    );
  });

  it("shows a load failure banner when the drafts request fails", async () => {
    server.use(
      http.get("/api/v1/drafts", () =>
        HttpResponse.json(
          { error: { code: "PTS_DRAFT_NOT_FOUND", message: "boom" } },
          { status: 500 },
        ),
      ),
    );
    renderPage();

    expect(await screen.findByText(copy.draftsLoadFailed)).toBeVisible();
  });
});
