import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { apiClient } from "../../api/client";
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
 * links to its editor; an empty state guides the user to create a dish.
 */
export function HomePage() {
  const copy = PRODUCT_COPY.zh;
  const query = useQuery({
    queryKey: ["drafts"],
    queryFn: loadDrafts,
  });

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
            </li>
          ))}
        </ul>
      </section>
    </main>
  );
}
