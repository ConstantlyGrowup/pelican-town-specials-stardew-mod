import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { apiClient, getCsrfToken } from "../../api/client";
import { GameUiIcon, SpecificIcon } from "../../components/ui/GameAssetIcon";
import { PixelModal } from "../../components/ui/PixelModal";
import type { components } from "../../api/generated/schema";
import { useCopy, useLocale } from "../../i18n/locale";
import type { Language } from "../../i18n/copy";

type DraftSortBy = "updatedAt" | "createdAt";
type DraftSortOrder = "desc" | "asc";

const PAGE_SIZE = 10;
const VALID_SORT_FIELDS: ReadonlySet<string> = new Set([
  "updatedAt",
  "createdAt",
]);
const VALID_SORT_ORDERS: ReadonlySet<string> = new Set(["desc", "asc"]);

type DraftsResponse = components["schemas"]["DraftPage"];

async function loadDrafts(params: {
  page: number;
  sortBy: DraftSortBy;
  sortOrder: DraftSortOrder;
}): Promise<DraftsResponse> {
  const { data, error } = await apiClient.GET("/api/v1/drafts", {
    params: {
      query: {
        page: params.page,
        pageSize: PAGE_SIZE,
        sortBy: params.sortBy,
        sortOrder: params.sortOrder,
      },
    },
  });
  if (error || !data) {
    throw new Error("load failed");
  }
  return data;
}

function formatTimestamp(value: string, locale: Language): string {
  const date = new Date(value);
  return date.toLocaleString(locale, {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

/**
 * Home dashboard: product identity plus a paginated, sortable list of saved
 * drafts (M13 Task 57). Each draft links to its editor and offers a delete
 * (discard) entry; an empty state guides the user to create a dish.
 *
 * URL state: page / sortBy / sortOrder live in the query string so a refresh
 * or a back/forward navigation restores the exact view. Invalid values are
 * normalized to the defaults with replace navigation, changing the sort
 * resets to page 1, and the server-clamped page is written back to the URL.
 */
export function HomePage({ pollIntervalMs = 2000 }: { pollIntervalMs?: number }) {
  const copy = useCopy();
  const locale = useLocale();
  const queryClient = useQueryClient();
  const [searchParams, setSearchParams] = useSearchParams();
  const [deleting, setDeleting] = useState<Set<string>>(new Set());
  const [confirmingDraftId, setConfirmingDraftId] = useState<string | null>(null);

  const rawSortBy = searchParams.get("sortBy") ?? "updatedAt";
  const rawSortOrder = searchParams.get("sortOrder") ?? "desc";
  const rawPage = Number(searchParams.get("page") ?? "1");
  const sortBy: DraftSortBy = VALID_SORT_FIELDS.has(rawSortBy)
    ? (rawSortBy as DraftSortBy)
    : "updatedAt";
  const sortOrder: DraftSortOrder = VALID_SORT_ORDERS.has(rawSortOrder)
    ? (rawSortOrder as DraftSortOrder)
    : "desc";
  const page = Number.isInteger(rawPage) && rawPage >= 1 ? rawPage : 1;

  const query = useQuery({
    queryKey: ["drafts", page, sortBy, sortOrder],
    queryFn: () => loadDrafts({ page, sortBy, sortOrder }),
  });
  const { isPending } = query;

  // The server clamps out-of-range requests (a deleted last item of a page or
  // a deep link past the end) to the last valid page; that effective page in
  // the response drives the pager and is normalized into the URL below.
  const effectivePage = query.data?.page ?? page;

  useEffect(() => {
    const next = new URLSearchParams(searchParams);
    let changed = false;
    const rawPageParam = searchParams.get("page");
    const rawSortByParam = searchParams.get("sortBy");
    const rawSortOrderParam = searchParams.get("sortOrder");

    // Keep a clean root URL while still replacing explicitly invalid values
    // instead of adding another browser-history entry.
    if (rawPageParam !== null && rawPageParam !== String(page)) {
      next.set("page", String(page));
      changed = true;
    }
    if (rawSortByParam !== null && rawSortByParam !== sortBy) {
      next.set("sortBy", sortBy);
      changed = true;
    }
    if (rawSortOrderParam !== null && rawSortOrderParam !== sortOrder) {
      next.set("sortOrder", sortOrder);
      changed = true;
    }

    // A successful response can clamp a deep link or a page that became
    // invalid after deleting its final draft. Persist that effective page so
    // refresh/back navigation returns to a valid view.
    const serverPage = query.data?.page;
    if (serverPage !== undefined && serverPage !== page && serverPage >= 1) {
      next.set("page", String(serverPage));
      changed = true;
    }

    if (changed) {
      setSearchParams(next, { replace: true });
    }
  }, [page, query.data?.page, searchParams, setSearchParams, sortBy, sortOrder]);


  // M13 Task 57: while ANY visible draft (including one on another page) is
  // generating server-side, keep the dashboard fresh so a just-finished
  // generation is reflected without a manual reload. The server flag covers
  // every page of the visible set; the first poll to observe it false after a
  // running sequence performs one final refresh so an off-page generation
  // finishing between polls is never left stale. The interval belongs to the
  // query key being shown: page/sort navigation tears it down and resets the
  // running history so stale transitions never fire extra requests.
  const hasRunningGeneration = query.data?.hasRunningGeneration ?? false;
  const pollingStateRef = useRef<{
    key: string;
    wasRunning: boolean;
  }>({ key: "", wasRunning: false });
  useEffect(() => {
    const pollingKey = `${page}:${sortBy}:${sortOrder}`;
    const state = pollingStateRef.current;
    const keyChanged = state.key !== pollingKey;
    const wasRunning = keyChanged ? false : state.wasRunning;
    pollingStateRef.current = { key: pollingKey, wasRunning: hasRunningGeneration };
    if (!hasRunningGeneration) {
      if (wasRunning && !keyChanged) {
        void queryClient.invalidateQueries({ queryKey: ["drafts"] });
      }
      return;
    }
    const interval = window.setInterval(() => {
      void queryClient.invalidateQueries({ queryKey: ["drafts"] });
    }, pollIntervalMs);
    return () => window.clearInterval(interval);
  }, [hasRunningGeneration, page, sortBy, sortOrder, pollIntervalMs, queryClient]);

  function applySort(nextSortBy: DraftSortBy, nextSortOrder: DraftSortOrder) {
    setSearchParams(
      { page: "1", sortBy: nextSortBy, sortOrder: nextSortOrder },
      { replace: false },
    );
  }

  function goToPage(nextPage: number) {
    setSearchParams({ page: String(nextPage), sortBy, sortOrder });
  }

  async function onConfirmDiscard(draftId: string) {
    setConfirmingDraftId(null);
    setDeleting((current) => new Set(current).add(draftId));
    const headers: Record<string, string> = {};
    const csrfToken = getCsrfToken();
    if (csrfToken) {
      headers["X-PTS-CSRF"] = csrfToken;
    }
    try {
      const response = await fetch(
        `/api/v1/drafts/${encodeURIComponent(draftId)}/discard`,
        { method: "POST", credentials: "same-origin", headers },
      );
      if (response.ok) {
        await queryClient.invalidateQueries({ queryKey: ["drafts"] });
      }
    } finally {
      setDeleting((current) => {
        const next = new Set(current);
        next.delete(draftId);
        return next;
      });
    }
  }

  const totalPages = query.data?.totalPages ?? 0;
  const total = query.data?.total ?? 0;
  const items = query.data?.items ?? [];
  const timestampKey =
    sortBy === "createdAt" ? "timestampCreatedPrefix" : "timestampUpdatedPrefix";
  const timestampLabel = copy[timestampKey];

  return (
    <main className="home-page" aria-labelledby="home-title">
      <section className="hero" aria-label={copy.heroAlt}>
        <div className="hero-media">
          <img
            src="/assets/ui/banner.jpg"
            alt={copy.heroAlt}
          />
        </div>
      </section>

      <section className="hero-copy hero-copy--standalone" aria-labelledby="home-title">
        <div>
          <p className="eyebrow">{copy.eyebrowKitchenLog}</p>
          <h1 id="home-title">{copy.createFirstDraft}</h1>
          <p>{copy.tagline}</p>
        </div>
        <div className="hero-copy__actions">
          <Link className="btn btn-primary" to="/create">
            <SpecificIcon name="createFirstDish" size={26} /> {copy.createFirstDraft}
          </Link>
          <Link className="btn btn-secondary" to="/cookbook">
            <GameUiIcon name="collections" size={20} /> {copy.cookbook}
          </Link>
        </div>
      </section>

      <section className="story-strip" aria-label={copy.storyStripLabel}>
        <div className="story-step">
          <span className="story-number">01</span>
          <span>
            <strong>{copy.storyStep1Title}</strong>
            <small>{copy.storyStep1Subtitle}</small>
          </span>
        </div>
        <div className="story-step">
          <span className="story-number">02</span>
          <span>
            <strong>{copy.storyStep2Title}</strong>
            <small>{copy.storyStep2Subtitle}</small>
          </span>
        </div>
        <div className="story-step">
          <span className="story-number">03</span>
          <span>
            <strong>{copy.storyStep3Title}</strong>
            <small>{copy.storyStep3Subtitle}</small>
          </span>
        </div>
      </section>

      <section aria-labelledby="create-mode-title">
        <div className="page-header">
          <div>
            <p className="eyebrow">{copy.eyebrowChooseWorkbench}</p>
            <h2 id="create-mode-title" className="section-title">{copy.homeCreateSectionTitle}</h2>
          </div>
          <p className="page-subtitle">{copy.homeCreateSectionSubtitle}</p>
        </div>
        <div className="mode-grid">
          <Link className="mode-card" to="/create">
            <span className="mode-icon mode-icon--portrait" aria-hidden="true">
              <img src="/assets/ui/gus-portrait-2.png" alt="" />
            </span>
            <span>
              <h2>{copy.askGus}</h2>
              <p>{copy.askGusCardText}</p>
            </span>
            <span className="btn btn-secondary">{copy.startAsking}</span>
          </Link>
          <Link className="mode-card blueprint-mode" to="/create">
            <span className="mode-icon" aria-hidden="true">
              <SpecificIcon name="blueprint" size={34} />
            </span>
            <span>
              <h2>{copy.blueprint}</h2>
              <p>{copy.blueprintCardText}</p>
            </span>
            <span className="btn">{copy.openWorkbench}</span>
          </Link>
        </div>
      </section>

      <section className="home-drafts" aria-labelledby="my-drafts-title">
        <div className="page-header">
          <div>
            <p className="eyebrow">{copy.eyebrowYourKitchenLog}</p>
            <h2 id="my-drafts-title" className="section-title">{copy.myDrafts}</h2>
          </div>
          <div className="draft-toolbar">
            <div className="draft-sort" role="group" aria-label={copy.draftSortLabel}>
              <button
                className={`btn btn-ghost draft-sort__field${sortBy === "updatedAt" ? " is-active" : ""}`}
                type="button"
                aria-pressed={sortBy === "updatedAt"}
                aria-label={
                  sortBy === "updatedAt"
                    ? copy.draftSortFieldActive
                        .replace("{field}", copy.sortUpdatedAt)
                        .replace(
                          "{direction}",
                          sortOrder === "desc"
                            ? copy.sortDirectionDesc
                            : copy.sortDirectionAsc,
                        )
                    : copy.sortUpdatedAt
                }
                onClick={() =>
                  applySort(
                    "updatedAt",
                    sortBy === "updatedAt" ? sortOrder : "desc",
                  )
                }
              >
                {copy.sortUpdatedAt}
              </button>
              <button
                className={`btn btn-ghost draft-sort__field${sortBy === "createdAt" ? " is-active" : ""}`}
                type="button"
                aria-pressed={sortBy === "createdAt"}
                aria-label={
                  sortBy === "createdAt"
                    ? copy.draftSortFieldActive
                        .replace("{field}", copy.sortCreatedAt)
                        .replace(
                          "{direction}",
                          sortOrder === "desc"
                            ? copy.sortDirectionDesc
                            : copy.sortDirectionAsc,
                        )
                    : copy.sortCreatedAt
                }
                onClick={() =>
                  applySort(
                    "createdAt",
                    sortBy === "createdAt" ? sortOrder : "desc",
                  )
                }
              >
                {copy.sortCreatedAt}
              </button>
              <button
                className={`btn btn-ghost draft-sort__field draft-sort__field--direction${sortOrder === "desc" ? " is-active" : ""}`}
                type="button"
                aria-pressed={sortOrder === "desc"}
                onClick={() =>
                  applySort(sortBy, sortOrder === "desc" ? "asc" : "desc")
                }
              >
                {sortOrder === "desc"
                  ? copy.sortDirectionDesc
                  : copy.sortDirectionAsc}
              </button>
            </div>
            <Link className="btn btn-ghost" to="/create">{copy.newDraft}</Link>
          </div>
        </div>
        {isPending && (
          <p className="status-banner status-info">{copy.loading}</p>
        )}
        {query.isError && query.data && (
          <div className="status-banner status-warning">{copy.draftsLoadFailed}</div>
        )}
        {query.isError && !query.data && (
          <div className="status-banner status-error">{copy.draftsLoadFailed}</div>
        )}
        {query.data && total === 0 && (
          <div className="empty-state">
            <p>{copy.draftsEmpty}</p>
            <Link className="btn btn-primary" to="/create">
              {copy.createFirstDraft}
            </Link>
          </div>
        )}
        <ul className="draft-grid" style={{ listStyle: "none", padding: 0 }}>
          {items.map((draft) => (
            <li key={draft.draftId} className="draft-card">
              <Link
                className="draft-card-main"
                to={`/drafts/${draft.draftId}`}
                aria-label={draft.displayName || copy.unnamedDraft}
              >
                <span
                  className={`draft-card-icon${draft.status === "ARCHIVED" ? " draft-card-icon--archived" : ""}`}
                  aria-hidden="true"
                >
                  {draft.status === "ARCHIVED" ? "✓" : draft.mode === "BLUEPRINT" ? "✎" : "?"}
                </span>
                <span>
                  <h3>{draft.displayName || copy.unnamedDraft}</h3>
                  <span className="draft-meta">
                    <span>{draft.mode === "BLUEPRINT" ? copy.blueprint : copy.askGus}</span>
                    <span className={`status-chip${draft.status === "FAILED" ? " error" : draft.status.includes("GENERATING") ? " generating" : ""}`}>
                      {copy.draftStatusLabels[draft.status] ?? draft.status}
                    </span>
                    <span>
                      {timestampLabel}{" "}
                      {formatTimestamp(
                        sortBy === "createdAt"
                          ? draft.createdAt
                          : draft.updatedAt,
                        locale,
                      )}
                    </span>
                  </span>
                </span>
              </Link>
              {draft.status !== "ARCHIVED" && draft.status !== "DISCARDED" && (
                <button
                  className="btn btn-ghost"
                  type="button"
                  onClick={() => setConfirmingDraftId(draft.draftId)}
                  disabled={deleting.has(draft.draftId)}
                >
                  {deleting.has(draft.draftId)
                    ? copy.discardingDraft
                    : copy.discardDraft}
                </button>
              )}
            </li>
          ))}
        </ul>
        {total > 0 && (
          <nav
            className="draft-pagination"
            aria-label={copy.myDrafts}
          >
            <button
              className="btn btn-ghost"
              type="button"
              onClick={() => goToPage(effectivePage - 1)}
              disabled={effectivePage <= 1}
            >
              {copy.previousPage}
            </button>
            <span
              className="draft-pagination__meta"
              role="status"
              aria-label={`${copy.pageIndicator
                .replace("{current}", String(effectivePage))
                .replace("{total}", String(Math.max(totalPages, 1)))}, ${copy.draftsCount.replace("{count}", String(total))}`}
            >
              {copy.pageIndicator
                .replace("{current}", String(effectivePage))
                .replace("{total}", String(Math.max(totalPages, 1)))}
              <span aria-hidden="true"> · </span>
              {copy.draftsCount.replace("{count}", String(total))}
            </span>
            <button
              className="btn btn-ghost"
              type="button"
              onClick={() => goToPage(effectivePage + 1)}
              disabled={effectivePage >= totalPages}
            >
              {copy.nextPage}
            </button>
          </nav>
        )}
      </section>

      <section className="feature-grid" aria-label={copy.quickLinksLabel}>
        <Link className="feature-link" to="/cookbook">
          <span className="mode-icon" aria-hidden="true">
            <GameUiIcon name="collections" size={30} />
          </span>
          <span>
            <h3>{copy.cookbook}</h3>
            <p>{copy.cookbookFeatureText}</p>
          </span>
          <span>{copy.viewCookbook}</span>
        </Link>
        <Link className="feature-link" to="/pack-menu">
          <span className="mode-icon" aria-hidden="true">
            <GameUiIcon name="gift" size={30} />
          </span>
          <span>
            <h3>{copy.packMenu}</h3>
            <p>{copy.packFeatureText}</p>
          </span>
          <span>{copy.preparePack}</span>
        </Link>
      </section>

      {confirmingDraftId && (
        <PixelModal
          title={copy.discardDraftTitle}
          description={copy.deleteDraftConfirm}
          onClose={() => setConfirmingDraftId(null)}
          footer={
            <>
              <button
                className="btn btn-danger"
                type="button"
                onClick={() => void onConfirmDiscard(confirmingDraftId)}
              >
                {copy.discardDraft}
              </button>
              <button className="btn" type="button" onClick={() => setConfirmingDraftId(null)}>
                {copy.cancelDelete}
              </button>
            </>
          }
        >
          <p>{copy.discardDraftMessage}</p>
        </PixelModal>
      )}
    </main>
  );
}
