import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { apiClient, assetUrl, getCsrfToken } from "../../api/client";
import { DownloadableImage } from "../../components/DownloadableImage";
import { GameObjectIcon } from "../../components/ui/GameAssetIcon";
import { PixelModal } from "../../components/ui/PixelModal";
import type { components } from "../../api/generated/schema";
import { useCopy } from "../../i18n/locale";
import { GenerationError } from "../generation/GenerationError";
import { GenerationProgress } from "../generation/GenerationProgress";
import { GenerationTimingBadge } from "../generation/GenerationTimingBadge";
import { TrialUsageBadge } from "../generation/TrialUsageBadge";
import { useGeneration } from "../generation/useGeneration";

type DraftView = components["schemas"]["DraftView"];

/**
 * Ask Gus review page. A REVIEWABLE draft offers exactly three operations:
 * accept (archive), full regeneration, and reject (discard). The blueprint
 * entry lives in the homepage create flow only. There are no partial visual
 * regeneration actions. A full regeneration keeps the previous REVIEWABLE
 * result on screen; failure restores it with an inline error and a retry entry.
 */
// The transient action error stores a catalog key so a live message
// re-localizes when the user switches the UI language (M7-T25-I18N-001).
type ReviewMessageKey =
  | "archiveFailed"
  | "discardFailed"
  | "providerPreferenceFailed";

export function AskGusReviewPage() {
  const { draftId } = useParams<{ draftId: string }>();
  const copy = useCopy();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [busy, setBusy] = useState(false);
  const [preferenceBusy, setPreferenceBusy] = useState(false);
  const [actionError, setActionError] = useState<ReviewMessageKey | null>(null);
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
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["draft", draftId] });
    },
  });

  async function setPersonalPreference(): Promise<boolean> {
    setPreferenceBusy(true);
    setActionError(null);
    const { data, error } = await apiClient.PUT(
      "/api/v1/settings/provider/trial/preference",
      { body: { mode: "PERSONAL" } },
    );
    setPreferenceBusy(false);
    if (error || !data) {
      setActionError("providerPreferenceFailed");
      return false;
    }
    return true;
  }

  async function onTakeoverPersonal() {
    if (await setPersonalPreference()) {
      generation.begin();
    }
  }

  async function onConfigurePersonal() {
    if (await setPersonalPreference()) {
      navigate("/settings");
    }
  }

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
      setActionError("archiveFailed");
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
      setActionError("discardFailed");
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
          <p className="eyebrow">{copy.eyebrowGusReview}</p>
          <h1>{copy.askGusReviewTitle}</h1>
        </div>
        <div className="gus-status-cluster">
          <img src="/assets/ui/gus-portrait-2.png" alt={copy.gusName} />
          <div className="draft-status-line">
            <span>{copy.modeLabel}</span>
            <strong>{copy.askGus}</strong>
            <span>{copy.statusLabel}</span>
            <strong>{copy.draftStatusLabels[draft.status] ?? draft.status}</strong>
          </div>
        </div>
      </div>
      <p className="gus-subtitle">
        {copy.draftSubtitleLine
          .replace("{mode}", copy.modeLabel)
          .replace("{modeValue}", copy.askGus)
          .replace("{status}", copy.statusLabel)
          .replace(
            "{statusValue}",
            copy.draftStatusLabels[draft.status] ?? draft.status,
          )
          .replace("{revision}", copy.revisionLabel)
          .replace("{revisionValue}", String(draft.revision))}
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
          onTakeover={canRetry ? onTakeoverPersonal : undefined}
          onConfigure={canRetry ? onConfigurePersonal : undefined}
          actionPending={preferenceBusy}
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
        <section className="gus-preview" aria-label={copy.previewResourceAria.replace("{name}", visualName)}>
          <div className="gus-preview__main">
            {previewUrl ? (
              <DownloadableImage
                src={previewUrl}
                alt={copy.previewImageAlt.replace("{name}", visualName)}
                downloadName={`${visualName}${copy.previewDownloadSuffix}`}
                style={{ maxWidth: "100%", height: "auto", display: "block" }}
              />
            ) : (
              <img src="/assets/ui/unknown-dish.png" alt={copy.waitingPreviewAlt} />
            )}
          </div>
          {iconUrl && (
            <div className="gus-preview__icon">
              <img
                src={iconUrl}
                alt={copy.iconImageAlt.replace("{name}", visualName)}
                width={64}
                height={64}
              />
              <span>{copy.iconMeta16}</span>
            </div>
          )}
        </section>

      <section className={`paper-panel gus-result-panel${waitingForResult ? " is-waiting" : ""}`}>
        <div className="gus-result-heading">
          <p className="eyebrow">{copy.eyebrowGusNotes}</p>
          <img src="/assets/ui/gus-portrait-1.png" alt={copy.gusPortraitAlt} />
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
        <GenerationTimingBadge
          timing={generation.timing}
          variant={
            generation.timing &&
            draft.provenance?.generationSource === "CANONICAL_REUSED"
              ? "gus"
              : "neutral"
          }
        />
        <TrialUsageBadge fact={generation.trialUsage} />
        {waitingForResult && (
          <div className="gus-waiting-note" role="status" aria-live="polite">
            <img src="/assets/ui/gus-portrait-1.png" alt={copy.gusName} />
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

      {terminal && (
        <p className="status-banner status-warning">
          {copy.draftTerminalStatusLine
            .replace("{title}", copy.draftTitle)
            .replace(
              "{status}",
              copy.draftStatusLabels[draft.status] ?? draft.status,
            )}
        </p>
      )}

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

      {actionError && <div className="status-banner status-error">{copy[actionError]}</div>}
      {confirmingDiscard && (
        <PixelModal
          title={copy.rejectDraftTitle}
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
          <p>{copy.rejectDraftMessage}</p>
        </PixelModal>
      )}
    </main>
  );
}
