import "@testing-library/jest-dom/vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { setupServer } from "msw/node";
import { MemoryRouter, useLocation } from "react-router-dom";
import { afterAll, afterEach, beforeAll, describe, expect, it, vi } from "vitest";
import { catalogs } from "../../i18n/copy";
import { HomePage } from "./HomePage";

const copy = catalogs["zh-CN"];

type DraftItem = {
  draftId: string;
  mode: string;
  status: string;
  revision: number;
  createdAt: string;
  updatedAt: string;
  displayName: string;
  originalImageAssetId: string;
};

function draftItem(overrides: Partial<DraftItem>): DraftItem {
  return {
    draftId: "draft-1",
    mode: "BLUEPRINT",
    status: "DRAFT",
    revision: 1,
    createdAt: "2026-08-01T00:00:00Z",
    updatedAt: "2026-08-04T00:00:00Z",
    displayName: "南瓜汤",
    originalImageAssetId: "asset-1",
    ...overrides,
  };
}

function draftPage(
  items: DraftItem[],
  overrides: Partial<{
    total: number;
    page: number;
    pageSize: number;
    totalPages: number;
    hasRunningGeneration: boolean;
  }> = {},
) {
  const total = overrides.total ?? items.length;
  const pageSize = overrides.pageSize ?? 10;
  const page = overrides.page ?? 1;
  return {
    items,
    nextCursor: null,
    total,
    page,
    pageSize,
    totalPages:
      overrides.totalPages ?? Math.max(Math.ceil(total / pageSize), 1),
    hasRunningGeneration: overrides.hasRunningGeneration ?? false,
  };
}

const defaultDrafts = [
  draftItem({
    draftId: "draft-1",
    mode: "BLUEPRINT",
    status: "DRAFT",
    updatedAt: "2026-08-04T00:00:00Z",
    displayName: "南瓜汤",
  }),
  draftItem({
    draftId: "draft-2",
    mode: "ASK_GUS",
    status: "REVIEWABLE",
    revision: 3,
    createdAt: "2026-08-02T00:00:00Z",
    updatedAt: "2026-08-03T00:00:00Z",
    displayName: "",
    originalImageAssetId: "asset-2",
  }),
];

const server = setupServer(
  http.get("/api/v1/drafts", () =>
    HttpResponse.json(draftPage(defaultDrafts)),
  ),
);

function LocationProbe() {
  const location = useLocation();
  return <div data-testid="home-location">{location.search}</div>;
}

beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
afterEach(() => {
  server.resetHandlers();
  vi.restoreAllMocks();
});
afterAll(() => server.close());

function renderPage(
  initialEntries = ["/"],
  pollIntervalMs?: number,
  includeLocationProbe = false,
) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={initialEntries}>
        <HomePage pollIntervalMs={pollIntervalMs} />
        {includeLocationProbe && <LocationProbe />}
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
        HttpResponse.json(draftPage([], { pageSize: 10, totalPages: 0 })),
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
    const afterDelete = defaultDrafts.slice(1);
    const getSpy = vi
      .fn()
      .mockReturnValueOnce(HttpResponse.json(draftPage(defaultDrafts)))
      .mockReturnValueOnce(HttpResponse.json(draftPage(afterDelete)));
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
        HttpResponse.json(
          draftPage([
            draftItem({
              draftId: "draft-archived",
              status: "ARCHIVED",
              revision: 2,
              displayName: "南瓜汤",
            }),
          ]),
        ),
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

describe("home page draft pagination and sorting (M13 Task 57)", () => {
  const elevenDrafts = Array.from({ length: 11 }, (_, index) =>
    draftItem({
      draftId: `draft-${index + 1}`,
      displayName: `草稿${index + 1}`,
      createdAt: `2026-08-${String(index + 1).padStart(2, "0")}T00:00:00Z`,
      updatedAt: `2026-09-${String(index + 1).padStart(2, "0")}T00:00:00Z`,
    }),
  );

  function servePagesByQuery() {
    server.use(
      http.get("/api/v1/drafts", ({ request }) => {
        const url = new URL(request.url);
        const rawPage = Number(url.searchParams.get("page") ?? "1");
        const page = Number.isInteger(rawPage) && rawPage >= 1 ? rawPage : 1;
        const start = (page - 1) * 10;
        const items = elevenDrafts.slice(start, start + 10);
        return HttpResponse.json(
          draftPage(items, {
            total: 11,
            page,
            pageSize: 10,
            totalPages: 2,
          }),
        );
      }),
    );
  }

  it("pages through more than one page of drafts with previous/next", async () => {
    servePagesByQuery();
    renderPage();

    // Page 1 shows the first ten; pagination meta says 1/2 and 共 11 条.
    expect(await screen.findByRole("heading", { name: "草稿1" })).toBeVisible();
    expect(screen.queryByRole("heading", { name: "草稿11" })).toBeNull();
    const prev = screen.getByRole("button", { name: copy.previousPage });
    const next = screen.getByRole("button", { name: copy.nextPage });
    expect(prev).toBeDisabled();
    expect(next).toBeEnabled();
    expect(screen.getByRole("status")).toHaveAccessibleName("第 1 / 2 页, 共 11 条");

    fireEvent.click(next);
    expect(await screen.findByRole("heading", { name: "草稿11" })).toBeVisible();
    expect(screen.queryByRole("heading", { name: "草稿1" })).toBeNull();
    expect(screen.getByRole("status")).toHaveAccessibleName("第 2 / 2 页, 共 11 条");
    expect(screen.getByRole("button", { name: copy.nextPage })).toBeDisabled();

    fireEvent.click(screen.getByRole("button", { name: copy.previousPage }));
    expect(await screen.findByRole("heading", { name: "草稿1" })).toBeVisible();
  });

  it("keeps page/sort in the URL query and restores it on remount", async () => {
    servePagesByQuery();
    const { unmount } = renderPage();
    await screen.findByRole("heading", { name: "草稿1" });
    fireEvent.click(screen.getByRole("button", { name: copy.nextPage }));
    await screen.findByRole("heading", { name: "草稿11" });

    unmount();
    renderPage(["/?page=2&sortBy=updatedAt&sortOrder=desc"]);
    expect(await screen.findByRole("heading", { name: "草稿11" })).toBeVisible();
    expect(screen.getByRole("status")).toHaveAccessibleName("第 2 / 2 页, 共 11 条");
  });

  it("changes the sort field and direction, sending page=1 queries", async () => {
    const requested: Array<{ sortBy: string | null; sortOrder: string | null; page: string | null }> = [];
    server.use(
      http.get("/api/v1/drafts", ({ request }) => {
        const url = new URL(request.url);
        requested.push({
          sortBy: url.searchParams.get("sortBy"),
          sortOrder: url.searchParams.get("sortOrder"),
          page: url.searchParams.get("page"),
        });
        const items = elevenDrafts.slice(0, 10);
        return HttpResponse.json(
          draftPage(items, {
            total: 11,
            page: 1,
            pageSize: 10,
            totalPages: 2,
          }),
        );
      }),
    );
    renderPage();
    await screen.findByRole("heading", { name: "草稿1" });

    fireEvent.click(screen.getByRole("button", { name: copy.sortCreatedAt }));
    await waitFor(() => expect(screen.getByRole("status")).toHaveAccessibleName("第 1 / 2 页, 共 11 条"));
    // The direction toggle starts in desc (active direction button labeled
    // "从新到旧") and flips to asc, relabeling itself "从旧到新".
    fireEvent.click(screen.getByRole("button", { name: copy.sortDirectionDesc }));
    await waitFor(() => expect(screen.getByRole("status")).toHaveAccessibleName("第 1 / 2 页, 共 11 条"));

    await waitFor(() => {
      const sortRequests = requested.filter((item) => item.page === "1");
      expect(sortRequests.length).toBeGreaterThanOrEqual(3);
    });
    const last = requested[requested.length - 1];
    expect(last.sortBy).toBe("createdAt");
    expect(last.sortOrder).toBe("asc");
    // The active created-time button reports its combined field + direction.
    expect(
      screen.getByRole("button", { name: `${copy.sortCreatedAt}：${copy.sortDirectionAsc}` }),
    ).toHaveAttribute("aria-pressed", "true");
    // The direction button now shows the applied ascending order.
    expect(
      screen.getByRole("button", { name: copy.sortDirectionAsc }),
    ).toBeVisible();
  });

  it("keeps polling while an off-page generation runs and refreshes once it ends", async () => {
    let calls = 0;
    server.use(
      http.get("/api/v1/drafts", () => {
        calls += 1;
        // The first responses report an off-page generation in flight; the
        // mock then reports it finished so the client stops polling.
        const running = calls <= 2;
        const items = defaultDrafts.map((draft) =>
          draft.status.includes("GENERATING") || running
            ? draft
            : draft,
        );
        return HttpResponse.json(
          draftPage(items, {
            hasRunningGeneration: running,
          }),
        );
      }),
    );
    // A tiny poll interval drives the refresh loop without fake timers.
    renderPage(["/"], 20);
    await screen.findByRole("heading", { name: "南瓜汤" });
    // While the flag is true the client keeps refreshing automatically.
    await waitFor(() => expect(calls).toBeGreaterThanOrEqual(3));
    expect(
      screen.getByRole("status"),
    ).toHaveAccessibleName("第 1 / 1 页, 共 2 条");
  });

  it("clamps an out-of-range page to the server-normalized page", async () => {
    server.use(
      http.get("/api/v1/drafts", () =>
        HttpResponse.json(
          draftPage([draftItem({ draftId: "only-draft" })], {
            total: 1,
            page: 1,
            pageSize: 10,
            totalPages: 1,
          }),
        ),
      ),
    );
    renderPage(["/?page=99"], undefined, true);
    await waitFor(() => {
      expect(screen.getByTestId("home-location")).toHaveTextContent(
        "?page=1",
      );
    });
    expect(await screen.findByRole("heading", { name: "南瓜汤" })).toBeVisible();
    expect(screen.getByRole("status")).toHaveAccessibleName("第 1 / 1 页, 共 1 条");
  });

  it("replaces invalid URL values with the normalized defaults", async () => {
    server.use(
      http.get("/api/v1/drafts", () =>
        HttpResponse.json(draftPage([draftItem({ draftId: "normalized" })])),
      ),
    );

    renderPage(["/?page=invalid&sortBy=unknown&sortOrder=sideways"], undefined, true);

    expect(await screen.findByRole("heading", { name: "南瓜汤" })).toBeVisible();
    await waitFor(() => {
      expect(screen.getByTestId("home-location")).toHaveTextContent(
        "?page=1&sortBy=updatedAt&sortOrder=desc",
      );
    });
  });

  it("replaces the URL with page one after deleting the final item on page two", async () => {
    let calls = 0;
    const discardSpy = vi.fn(() => new Response(null, { status: 204 }));
    server.use(
      http.get("/api/v1/drafts", () => {
        calls += 1;
        if (calls === 1) {
          return HttpResponse.json(
            draftPage([draftItem({ draftId: "last-draft", displayName: "最后一条" })], {
              total: 11,
              page: 2,
              pageSize: 10,
              totalPages: 2,
            }),
          );
        }
        return HttpResponse.json(
          draftPage(
            Array.from({ length: 10 }, (_, index) =>
              draftItem({ draftId: `remaining-${index + 1}`, displayName: `剩余${index + 1}` }),
            ),
            { total: 10, page: 1, pageSize: 10, totalPages: 1 },
          ),
        );
      }),
      http.post("/api/v1/drafts/:draft_id/discard", discardSpy),
    );

    renderPage(["/?page=2&sortBy=updatedAt&sortOrder=desc"], undefined, true);
    expect(await screen.findByRole("heading", { name: "最后一条" })).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: copy.discardDraft }));
    const dialog = screen.getByRole("dialog", { name: "放弃这份草稿？" });
    fireEvent.click(within(dialog).getByRole("button", { name: copy.discardDraft }));

    await waitFor(() => expect(discardSpy).toHaveBeenCalledTimes(1));
    await waitFor(() => {
      expect(screen.getByTestId("home-location")).toHaveTextContent(
        "?page=1&sortBy=updatedAt&sortOrder=desc",
      );
    });
    await waitFor(() => {
      expect(screen.getByRole("status")).toHaveAccessibleName("第 1 / 1 页, 共 10 条");
    });
  });
});
