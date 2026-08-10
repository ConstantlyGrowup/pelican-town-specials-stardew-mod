import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { apiClient, assetUrl } from "../../api/client";
import { uploadImage } from "../../api/uploadImage";
import type { components } from "../../api/generated/schema";
import { SpecificIcon } from "../../components/ui/GameAssetIcon";
import { useCopy, useLocale } from "../../i18n/locale";

type DraftMode = components["schemas"]["DraftMode"];

// The transient upload/create error stores a catalog key so a live message
// re-localizes when the user switches the UI language (M7-T25-I18N-001).
type CreateMessageKey = "uploadFailed" | "createFailed";

export function CreateDishPage() {
  const copy = useCopy();
  const locale = useLocale();
  const navigate = useNavigate();
  const [assetId, setAssetId] = useState<string | null>(null);
  const [mode, setMode] = useState<DraftMode>("ASK_GUS");
  const [contextText, setContextText] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<CreateMessageKey | null>(null);

  async function onFileChange(event: React.ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (!file) {
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const asset = await uploadImage(file);
      setAssetId(asset.assetId);
    } catch {
      setError("uploadFailed");
    } finally {
      setBusy(false);
    }
  }

  async function onCreate() {
    if (!assetId) {
      return;
    }
    setBusy(true);
    setError(null);
    const trimmedContext = contextText.trim();
    const { data, error: createError } = await apiClient.POST("/api/v1/drafts", {
      body: {
        mode,
        language: locale,
        source: {
          originalImageAssetId: assetId,
          contextText: trimmedContext ? trimmedContext : undefined,
        },
      },
    });
    setBusy(false);
    if (createError || !data) {
      setError("createFailed");
      return;
    }
    navigate(`/drafts/${data.draftId}`);
  }

  return (
    <main className="create-page">
      <div className="page-header">
        <div>
          <p className="eyebrow">{copy.eyebrowNewRecipe}</p>
          <h1>{copy.createTitle}</h1>
        </div>
        <p className="page-subtitle">{copy.createSubtitle}</p>
      </div>
      <section className="paper-panel upload-layout">
        <div>
          <div className={`upload-slot${assetId ? " has-image" : ""}`}>
            {assetId && assetUrl(assetId) ? (
              <img src={assetUrl(assetId) ?? undefined} alt={copy.uploadedImageAlt} />
            ) : (
              <div className="upload-placeholder">
                <span className="upload-placeholder__mark" aria-hidden="true">+</span>
                <strong>{copy.uploadLabel}</strong>
                <small>{copy.uploadHint}</small>
              </div>
            )}
            <label className="btn btn-secondary upload-action" htmlFor="dishPhoto">
              {busy ? copy.uploading : assetId ? copy.replacePhoto : copy.selectImage}
            </label>
          </div>
          <input
            id="dishPhoto"
            className="visually-hidden"
            aria-label={copy.uploadLabel}
            type="file"
            accept="image/png,image/jpeg,image/jpg,image/webp,.png,.jpg,.jpeg,.webp"
            onChange={onFileChange}
          />
          {assetId && <p className="status-banner status-success" role="status">{copy.uploadComplete}</p>}
        </div>

        <div className="upload-form">
          <div className="page-header page-header-compact">
            <div>
              <p className="eyebrow">{copy.eyebrowChoosePath}</p>
              <h2>{copy.choosePathTitle}</h2>
            </div>
            <span className="field-counter">{assetId ? copy.sourceReady : copy.waitingForPhoto}</span>
          </div>
          <div className="mode-choice-row" role="group" aria-label={copy.modeGroupLabel}>
            <button
              type="button"
              className="mode-choice"
              aria-pressed={mode === "ASK_GUS"}
              aria-label={copy.createAskGus}
              onClick={() => setMode("ASK_GUS")}
            >
              <span className="mode-choice__icon mode-choice__icon--portrait" aria-hidden="true">
                <img src="/assets/ui/gus-portrait-2.png" alt="" />
              </span>
              <span>
                <strong>{copy.createAskGus}</strong>
                <small>{copy.askGusChoiceText}</small>
              </span>
            </button>
            <button
              type="button"
              className="mode-choice blueprint-choice"
              aria-pressed={mode === "BLUEPRINT"}
              aria-label={copy.createBlueprint}
              onClick={() => setMode("BLUEPRINT")}
            >
              <span className="mode-choice__icon" aria-hidden="true">
                <SpecificIcon name="blueprint" size={28} />
              </span>
              <span>
                <strong>{copy.createBlueprint}</strong>
                <small>{copy.blueprintChoiceText}</small>
              </span>
            </button>
          </div>
          {mode === "BLUEPRINT" && (
            <div className="status-banner status-warning">
              <span className="status-icon" aria-hidden="true">!</span>
              <span>{copy.blueprintFromOriginalOnly}</span>
            </div>
          )}

          <div className="field">
            <label htmlFor="contextText">{copy.contextTextLabel}</label>
            <textarea
              id="contextText"
              value={contextText}
              maxLength={500}
              placeholder={copy.contextTextPlaceholder}
              onChange={(event) => setContextText(event.target.value)}
            />
            <span className="field-counter">{contextText.length} / 500</span>
          </div>

          {error && <div className="status-banner status-error">{copy[error]}</div>}
          <div className="action-row">
            <button
              className="btn btn-primary"
              type="button"
              onClick={onCreate}
              disabled={!assetId || busy}
              aria-label={busy ? copy.creating : copy.createDraft}
            >
              {busy ? copy.creating : copy.createDraft} →
            </button>
          </div>
        </div>
      </section>
    </main>
  );
}
