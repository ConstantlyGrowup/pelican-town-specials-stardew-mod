import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { apiClient, assetUrl, getCsrfToken } from "../../api/client";
import type { components } from "../../api/generated/schema";
import { PRODUCT_COPY } from "../../i18n/copy";
import { GenerationError } from "../generation/GenerationError";
import { GenerationProgress } from "../generation/GenerationProgress";
import { useGeneration } from "../generation/useGeneration";

type DraftView = components["schemas"]["DraftView"];

/**
 * Ask Gus review page. A REVIEWABLE draft offers exactly four operations:
 * accept (archive), full regeneration, reject (discard), and convert to
 * Blueprint. There are no partial visual regeneration actions. A full
 * regeneration keeps the previous REVIEWABLE result on screen; failure restores
 * it with an inline error and a retry entry.
 */
export function AskGusReviewPage() {
  const { draftId } = useParams<{ draftId: string }>();
  const copy = PRODUCT_COPY.zh;
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [busy, setBusy] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);

  const query = useQuery({
    queryKey: ["draft", draftId],
    queryFn: async (): Promise<DraftView> => {
      const { data, error } = await apiClient.GET("/api/v1/drafts/{draft_id}", {
        params: { path: { draft_id: draftId ?? "" } },
      });
      if (error || !data) {
        throw new Error("load failed");
      }
      return data;
    },
    enabled: Boolean(draftId),
  });

  const generation = useGeneration({
    draftId: draftId ?? "",
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["draft", draftId] });
    },
  });

  async function onArchive() {
    setBusy(true);
    setActionError(null);
    const { data, error } = await apiClient.POST(
      "/api/v1/drafts/{draft_id}/archive",
      {
        params: {
          path: { draft_id: draftId ?? "" },
          header: { "Idempotency-Key": crypto.randomUUID() },
        },
      },
    );
    setBusy(false);
    if (error || !data) {
      setActionError(copy.archiveFailed);
      return;
    }
    navigate(`/cookbook/${data.dishId}`);
  }

  async function onDiscard() {
    if (!window.confirm(copy.discardDraftConfirm)) {
      return;
    }
    setBusy(true);
    setActionError(null);
    const headers: Record<string, string> = {};
    const csrfToken = getCsrfToken();
    if (csrfToken) {
      headers["X-PTS-CSRF"] = csrfToken;
    }
    const response = await fetch(
      `/api/v1/drafts/${encodeURIComponent(draftId ?? "")}/discard`,
      { method: "POST", credentials: "same-origin", headers },
    );
    setBusy(false);
    if (!response.ok) {
      setActionError(copy.discardFailed);
      return;
    }
    navigate("/");
  }

  async function onConvertToBlueprint() {
    setBusy(true);
    setActionError(null);
    const { data, error } = await apiClient.POST(
      "/api/v1/drafts/{draft_id}/convert-to-blueprint",
      { params: { path: { draft_id: draftId ?? "" } } },
    );
    setBusy(false);
    if (error || !data) {
      setActionError(copy.convertFailed);
      return;
    }
    navigate(`/drafts/${data.draftId}`);
  }

  if (query.isLoading) {
    return (
      <main>
        <h1>{copy.askGusReviewTitle}</h1>
        <p>{copy.loading}</p>
      </main>
    );
  }

  if (query.isError || !query.data) {
    return (
      <main>
        <h1>{copy.draftNotFound}</h1>
      </main>
    );
  }

  const draft = query.data;
  const streaming = generation.phase === "streaming";
  // Initial generation is reachable from DRAFT/READY; a FAILED draft retries
  // through the same full INITIAL re-run path (the backend maps FAILED →
  // INITIAL). A terminal ARCHIVED/DISCARDED draft offers no generation entry.
  const canGenerate =
    draft.status === "DRAFT" ||
    draft.status === "READY" ||
    draft.status === "FAILED";
  const canRetry = canGenerate || draft.status === "REVIEWABLE";
  const running =
    draft.status === "GENERATING" || draft.status === "REGENERATING";
  const terminal = draft.status === "ARCHIVED" || draft.status === "DISCARDED";
  const previewUrl = assetUrl(draft.visuals?.previewAssetId);
  const iconUrl = assetUrl(draft.visuals?.icon16AssetId);
  const visualName = draft.presentation?.displayName ?? copy.draftTitle;

  return (
    <main>
      <h1>{copy.askGusReviewTitle}</h1>
      <p>
        {copy.modeLabel}：{copy.askGus}；{copy.statusLabel}：{draft.status}；{copy.revisionLabel}：
        {draft.revision}
      </p>

      {streaming && (
        <GenerationProgress
          currentStage={generation.currentStage}
          succeededStages={generation.succeededStages}
          totalStages={generation.totalStages}
          preparingLabel={copy.preparingNewResult}
          onCancel={generation.cancel}
        />
      )}
      {generation.phase === "error" && generation.error && (
        <GenerationError
          error={generation.error}
          onRetry={canRetry ? generation.begin : undefined}
        />
      )}
      {generation.phase === "cancelled" && (
        <p className="status-banner status-warning">{copy.generationCancelled}</p>
      )}
      {running && (
        <div className="status-banner status-warning">
          <p>{copy.generationInProgress}</p>
          <button
            className="btn"
            type="button"
            onClick={() =>
              void queryClient.invalidateQueries({ queryKey: ["draft", draftId] })
            }
          >
            {copy.refreshDraft}
          </button>
        </div>
      )}

      {(previewUrl || iconUrl) && (
        <section className="card" aria-label={`${visualName}预览资源`}>
          {previewUrl && (
            <img
              src={previewUrl}
              alt={`${visualName}预览`}
              style={{ maxWidth: "100%", height: "auto", display: "block" }}
            />
          )}
          {iconUrl && (
            <img
              src={iconUrl}
              alt={`${visualName}像素图标`}
              width={32}
              height={32}
              style={{ imageRendering: "pixelated", display: "block" }}
            />
          )}
        </section>
      )}

      <section className="card">
        {draft.presentation && (
          <>
            <h2>{draft.presentation.displayName}</h2>
            <p>{draft.presentation.description}</p>
          </>
        )}
        {draft.gameplay && (
          <ul>
            {draft.gameplay.ingredients.map((ingredient) => (
              <li key={ingredient.itemId}>
                {ingredient.displayName} × {ingredient.quantity}
              </li>
            ))}
          </ul>
        )}
        {!draft.presentation && !draft.gameplay && (
          <p>{copy.noGameplayYet}</p>
        )}
      </section>

      {terminal && <p className="status-banner status-warning">{copy.draftTitle}：{draft.status}</p>}

      {canGenerate && (
        <button
          className="btn btn-primary"
          type="button"
          onClick={generation.begin}
          disabled={streaming || busy}
        >
          {draft.status === "FAILED" ? copy.retryGeneration : copy.startGeneration}
        </button>
      )}

      {draft.status === "REVIEWABLE" && (
        <div className="card">
          <button
            className="btn btn-primary"
            type="button"
            onClick={onArchive}
            disabled={busy || streaming}
          >
            {copy.archiveDish}
          </button>
          <button className="btn" type="button" onClick={generation.begin} disabled={streaming}>
            {copy.fullRegenerate}
          </button>
          <button
            className="btn"
            type="button"
            onClick={onConvertToBlueprint}
            disabled={busy || streaming}
          >
            {copy.convertToBlueprint}
          </button>
          <button
            className="btn"
            type="button"
            onClick={onDiscard}
            disabled={busy || streaming}
          >
            {copy.rejectDraft}
          </button>
        </div>
      )}

      {actionError && <div className="status-banner status-error">{actionError}</div>}
    </main>
  );
}
