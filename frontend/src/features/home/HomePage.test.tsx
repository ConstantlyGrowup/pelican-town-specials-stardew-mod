import "@testing-library/jest-dom/vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { setupServer } from "msw/node";
import { MemoryRouter } from "react-router-dom";
import { afterAll, afterEach, beforeAll, describe, expect, it, vi } from "vitest";
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
afterEach(() => {
  server.resetHandlers();
  vi.restoreAllMocks();
});
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
    const { container } = renderPage();

    expect(screen.getByRole("heading", { name: copy.createFirstDraft })).toBeVisible();
    expect(screen.getByText(copy.tagline)).toBeVisible();
    expect(screen.getByRole("heading", { name: copy.myDrafts })).toBeVisible();
    expect(container.querySelector(".hero-media .hero-copy")).toBeNull();
    expect(container.querySelector(".hero-copy--standalone")).not.toBeNull();
    expect(container.querySelector('img[src="/assets/ui/gus-portrait-2.png"]')).not.toBeNull();
    expect(container.querySelector(".specific-icon--createFirstDish")).not.toBeNull();
    expect(container.querySelector(".specific-icon--blueprint")).not.toBeNull();
    expect(container.querySelector(".feature-link .game-ui-icon--collections")).not.toBeNull();
    expect(container.querySelector(".feature-link .game-ui-icon--gift")).not.toBeNull();

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
    const emptyState = screen.getByText(copy.draftsEmpty).closest(".empty-state");
    expect(emptyState).not.toBeNull();
    expect(within(emptyState as HTMLElement).getByRole("link", { name: copy.createFirstDraft })).toHaveAttribute(
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

  it("deletes a draft after confirmation and refreshes the list", async () => {
    const discardSpy = vi.fn(() => new Response(null, { status: 204 }));
    const getSpy = vi
      .fn()
      .mockReturnValueOnce(
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
      )
      .mockReturnValueOnce(
        HttpResponse.json({
          items: [
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
          total: 1,
        }),
      );
    server.use(
      http.get("/api/v1/drafts", getSpy),
      http.post("/api/v1/drafts/:draft_id/discard", discardSpy),
    );
    renderPage();

    await screen.findByRole("heading", { name: "南瓜汤" });
    const deleteButtons = screen.getAllByRole("button", {
      name: copy.discardDraft,
    });
    fireEvent.click(deleteButtons[0]);

    const dialog = screen.getByRole("dialog", { name: "放弃这份草稿？" });
    expect(within(dialog).getByText(copy.deleteDraftConfirm)).toBeVisible();
    fireEvent.click(within(dialog).getByRole("button", { name: copy.discardDraft }));
    await waitFor(() => expect(discardSpy).toHaveBeenCalledTimes(1));
    expect(await screen.findByText(copy.unnamedDraft)).toBeVisible();
    expect(screen.queryByRole("heading", { name: "南瓜汤" })).toBeNull();
    expect(getSpy).toHaveBeenCalledTimes(2);
  });

  it("does not delete when confirmation is cancelled", async () => {
    const discardSpy = vi.fn(() => new Response(null, { status: 204 }));
    server.use(
      http.post("/api/v1/drafts/:draft_id/discard", discardSpy),
    );
    renderPage();

    await screen.findByRole("heading", { name: "南瓜汤" });
    fireEvent.click(
      screen.getAllByRole("button", { name: copy.discardDraft })[0],
    );

    const dialog = screen.getByRole("dialog", { name: "放弃这份草稿？" });
    fireEvent.click(within(dialog).getByRole("button", { name: "取消" }));
    expect(discardSpy).not.toHaveBeenCalled();
  });

  it("hides the delete entry for ARCHIVED drafts", async () => {
    server.use(
      http.get("/api/v1/drafts", () =>
        HttpResponse.json({
          items: [
            {
              draftId: "draft-archived",
              mode: "BLUEPRINT",
              status: "ARCHIVED",
              revision: 2,
              updatedAt: "2026-08-04T00:00:00Z",
              displayName: "南瓜汤",
              originalImageAssetId: "asset-1",
            },
          ],
          nextCursor: null,
          total: 1,
        }),
      ),
    );
    const { container } = renderPage();

    await screen.findByRole("heading", { name: "南瓜汤" });
    expect(
      screen.queryByRole("button", { name: copy.discardDraft }),
    ).toBeNull();
    expect(container.querySelector(".draft-card-icon--archived")).toHaveTextContent("✓");
  });
});
