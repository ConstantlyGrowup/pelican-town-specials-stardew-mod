import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { apiClient, assetUrl, getCsrfToken } from "../../api/client";
import { DownloadableImage } from "../../components/DownloadableImage";
import { GameObjectIcon } from "../../components/ui/GameAssetIcon";
import { PixelModal } from "../../components/ui/PixelModal";
import type { components } from "../../api/generated/schema";
import { PRODUCT_COPY } from "../../i18n/copy";
import { GenerationError } from "../generation/GenerationError";
import { GenerationProgress } from "../generation/GenerationProgress";
import { useGeneration } from "../generation/useGeneration";

type DraftView = components["schemas"]["DraftView"];

/**
 * Ask Gus review page. A REVIEWABLE draft offers exactly three operations:
 * accept (archive), full regeneration, and reject (discard). The blueprint
 * entry lives in the homepage create flow only. There are no partial visual
 * regeneration actions. A full regeneration keeps the previous REVIEWABLE
 * result on screen; failure restores it with an inline error and a retry entry.
 */
export function AskGusReviewPage() {
  const { draftId } = useParams<{ draftId: string }>();
  const copy = PRODUCT_COPY.zh;
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [busy, setBusy] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);
  const [confirmingDiscard, setConfirmingDiscard] = useState(false);

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
    running:
      query.data?.status === "GENERATING" ||
      query.data?.status === "REGENERATING",
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

  async function onConfirmDiscard() {
    setConfirmingDiscard(false);
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
  const waitingForResult = !draft.presentation && !terminal;

  return (
    <main className="gus-page">
      <div className="page-header gus-page-header">
        <div>
          <p className="eyebrow">GUS REVIEW / TAVERN COUNTER</p>
          <h1>{copy.askGusReviewTitle}</h1>
        </div>
        <div className="gus-status-cluster">
          <img src="/assets/ui/gus-portrait-2.png" alt="Gus" />
          <div className="draft-status-line">
            <span>{copy.modeLabel}</span>
            <strong>{copy.askGus}</strong>
            <span>{copy.statusLabel}</span>
            <strong>{draft.status}</strong>
          </div>
        </div>
      </div>
      <p className="gus-subtitle">
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
      {running && generation.phase !== "streaming" && (
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
          <button className="btn" type="button" onClick={() => void generation.cancel()}>
            {copy.cancelGeneration}
          </button>
        </div>
      )}

      <div className="gus-layout">
        <section className="gus-preview" aria-label={`${visualName}预览资源`}>
          <div className="gus-preview__main">
            {previewUrl ? (
              <DownloadableImage
                src={previewUrl}
                alt={`${visualName}预览`}
                downloadName={`${visualName}-预览`}
                style={{ maxWidth: "100%", height: "auto", display: "block" }}
              />
            ) : (
              <img src="/assets/ui/unknown-dish.png" alt="等待 Gus 生成菜品预览" />
            )}
          </div>
          {iconUrl && (
            <div className="gus-preview__icon">
              <img
                src={iconUrl}
                alt={`${visualName}像素图标`}
                width={64}
                height={64}
              />
              <span>16 × 16 / 游戏图标</span>
            </div>
          )}
        </section>

      <section className={`paper-panel gus-result-panel${waitingForResult ? " is-waiting" : ""}`}>
        <div className="gus-result-heading">
          <p className="eyebrow">GUS'S NOTES / RESULT CARD</p>
          <img src="/assets/ui/gus-portrait-1.png" alt="Gus 的点评头像" />
        </div>
        {draft.presentation && (
          <>
            <h2 className="result-title">{draft.presentation.displayName}</h2>
            <div className="gus-comment">
              <p>{draft.presentation.description}</p>
              {draft.presentation.gusComment && <p>{draft.presentation.gusComment}</p>}
            </div>
          </>
        )}
        {waitingForResult && (
          <div className="gus-waiting-note" role="status" aria-live="polite">
            <img src="/assets/ui/gus-portrait-1.png" alt="Gus" />
            <div>
              <h2>{copy.gusWaitingTitle}</h2>
              <p>{copy.gusWaitingMessage}</p>
              <p>{copy.gusWaitingDetail}</p>
            </div>
          </div>
        )}
        {draft.gameplay && (
          <ul className="ingredient-list">
            {draft.gameplay.ingredients.map((ingredient) => (
              <li key={ingredient.itemId} className="ingredient-row">
                <span className="ingredient-row__content">
                  <GameObjectIcon itemId={ingredient.itemId} size={32} />
                  <span>{ingredient.displayName}</span>
                </span>
                <strong>× {ingredient.quantity}</strong>
              </li>
            ))}
          </ul>
        )}
      </section>
      </div>

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
        <div className="card gus-actions">
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
            onClick={() => setConfirmingDiscard(true)}
            disabled={busy || streaming}
          >
            {copy.rejectDraft}
          </button>
        </div>
      )}

      {actionError && <div className="status-banner status-error">{actionError}</div>}
      {confirmingDiscard && (
        <PixelModal
          title="拒绝这份草稿？"
          description={copy.discardDraftConfirm}
          onClose={() => setConfirmingDiscard(false)}
          footer={
            <>
              <button className="btn btn-danger" type="button" onClick={() => void onConfirmDiscard()}>
                {copy.rejectDraft}
              </button>
              <button className="btn" type="button" onClick={() => setConfirmingDiscard(false)}>
                {copy.cancelDelete}
              </button>
            </>
          }
        >
          <p>拒绝后，这份草稿和上传的素材都不会再出现在工作区。</p>
        </PixelModal>
      )}
    </main>
  );
}
