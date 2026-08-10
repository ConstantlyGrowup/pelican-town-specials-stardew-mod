import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { apiClient, getCsrfToken } from "../../api/client";
import { GameUiIcon, SpecificIcon } from "../../components/ui/GameAssetIcon";
import { PixelModal } from "../../components/ui/PixelModal";
import type { components } from "../../api/generated/schema";
import { useCopy, useLocale } from "../../i18n/locale";
import type { Language } from "../../i18n/copy";

type DraftSummary = components["schemas"]["DraftSummary"];

async function loadDrafts(): Promise<DraftSummary[]> {
  const { data, error } = await apiClient.GET("/api/v1/drafts");
  if (error || !data) {
    throw new Error("load failed");
  }
  return data.items;
}

function formatUpdatedAt(value: string, locale: Language): string {
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
 * Home dashboard: product identity plus a list of saved drafts. Each draft
 * links to its editor and offers a delete (discard) entry; an empty state
 * guides the user to create a dish.
 */
export function HomePage() {
  const copy = useCopy();
  const locale = useLocale();
  const queryClient = useQueryClient();
  const [deleting, setDeleting] = useState<Set<string>>(new Set());
  const [confirmingDraftId, setConfirmingDraftId] = useState<string | null>(null);
  const query = useQuery({
    queryKey: ["drafts"],
    queryFn: loadDrafts,
  });

  // Task 19.5: while any listed draft is generating server-side, keep the
  // dashboard fresh so a just-finished generation is reflected without a manual
  // reload. The interval is torn down when nothing is generating or on unmount.
  const hasRunningGeneration =
    query.data?.some(
      (draft) =>
        draft.status === "GENERATING" || draft.status === "REGENERATING",
    ) ?? false;
  useEffect(() => {
    if (!hasRunningGeneration) {
      return;
    }
    const interval = window.setInterval(() => {
      void queryClient.invalidateQueries({ queryKey: ["drafts"] });
    }, 2000);
    return () => window.clearInterval(interval);
  }, [hasRunningGeneration, queryClient]);

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
          <Link className="btn btn-ghost" to="/create">{copy.newDraft}</Link>
        </div>
        {query.isLoading && <p className="status-banner status-info">{copy.loading}</p>}
        {query.isError && (
          <div className="status-banner status-error">{copy.draftsLoadFailed}</div>
        )}
        {query.data && query.data.length === 0 && (
          <div className="empty-state">
            <p>{copy.draftsEmpty}</p>
            <Link className="btn btn-primary" to="/create">
              {copy.createFirstDraft}
            </Link>
          </div>
        )}
        <ul className="draft-grid" style={{ listStyle: "none", padding: 0 }}>
          {query.data?.map((draft) => (
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
                    <span>{formatUpdatedAt(draft.updatedAt, locale)}</span>
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
