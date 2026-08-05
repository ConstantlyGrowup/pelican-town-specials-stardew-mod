import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router-dom";
import { apiClient, getCsrfToken } from "../../api/client";
import type { components } from "../../api/generated/schema";
import { PRODUCT_COPY } from "../../i18n/copy";

type DraftSummary = components["schemas"]["DraftSummary"];

async function loadDrafts(): Promise<DraftSummary[]> {
  const { data, error } = await apiClient.GET("/api/v1/drafts");
  if (error || !data) {
    throw new Error("load failed");
  }
  return data.items;
}

function formatUpdatedAt(value: string): string {
  const date = new Date(value);
  return date.toLocaleString("zh-CN", {
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
  const copy = PRODUCT_COPY.zh;
  const queryClient = useQueryClient();
  const [deleting, setDeleting] = useState<Set<string>>(new Set());
  const query = useQuery({
    queryKey: ["drafts"],
    queryFn: loadDrafts,
  });

  async function onDiscard(draftId: string) {
    if (!window.confirm(copy.deleteDraftConfirm)) {
      return;
    }
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
    <main aria-labelledby="app-title">
      <p lang="en">Pelican Town Specials</p>
      <h1 id="app-title">{copy.productName}</h1>
      <p>{copy.tagline}</p>
      <section aria-labelledby="my-drafts-title">
        <h2 id="my-drafts-title">{copy.myDrafts}</h2>
        {query.isLoading && <p>{copy.loading}</p>}
        {query.isError && (
          <div className="status-banner status-error">{copy.draftsLoadFailed}</div>
        )}
        {query.data && query.data.length === 0 && (
          <div className="card">
            <p>{copy.draftsEmpty}</p>
            <Link className="btn btn-primary" to="/create">
              {copy.createFirstDraft}
            </Link>
          </div>
        )}
        <ul style={{ listStyle: "none", padding: 0 }}>
          {query.data?.map((draft) => (
            <li key={draft.draftId} className="card" style={{ marginBottom: 12 }}>
              <Link to={`/drafts/${draft.draftId}`}>
                <h2>{draft.displayName || copy.unnamedDraft}</h2>
              </Link>
              <p>
                <span>
                  {draft.mode === "BLUEPRINT" ? copy.blueprint : copy.askGus}
                </span>
                {" · "}
                <span>{copy.draftStatusLabels[draft.status] ?? draft.status}</span>
                {" · "}
                <span>{formatUpdatedAt(draft.updatedAt)}</span>
              </p>
              {draft.status !== "ARCHIVED" && draft.status !== "DISCARDED" && (
                <button
                  className="btn"
                  type="button"
                  onClick={() => void onDiscard(draft.draftId)}
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
    </main>
  );
}
