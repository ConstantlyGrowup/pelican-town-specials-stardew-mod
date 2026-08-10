import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { apiClient, assetUrl } from "../../api/client";
import { uploadImage } from "../../api/uploadImage";
import type { components } from "../../api/generated/schema";
import { SpecificIcon } from "../../components/ui/GameAssetIcon";
import { PRODUCT_COPY } from "../../i18n/copy";

type DraftMode = components["schemas"]["DraftMode"];

export function CreateDishPage() {
  const copy = PRODUCT_COPY.zh;
  const navigate = useNavigate();
  const [assetId, setAssetId] = useState<string | null>(null);
  const [mode, setMode] = useState<DraftMode>("ASK_GUS");
  const [contextText, setContextText] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

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
      setError(copy.uploadFailed);
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
        language: "zh-CN",
        source: {
          originalImageAssetId: assetId,
          contextText: trimmedContext ? trimmedContext : undefined,
        },
      },
    });
    setBusy(false);
    if (createError || !data) {
      setError(copy.createFailed);
      return;
    }
    navigate(`/drafts/${data.draftId}`);
  }

  return (
    <main className="create-page">
      <div className="page-header">
        <div>
          <p className="eyebrow">NEW RECIPE / SOURCE MATERIAL</p>
          <h1>{copy.createTitle}</h1>
        </div>
        <p className="page-subtitle">先留下照片，再决定让谁来写这张菜单。</p>
      </div>
      <section className="paper-panel upload-layout">
        <div>
          <div className={`upload-slot${assetId ? " has-image" : ""}`}>
            {assetId && assetUrl(assetId) ? (
              <img src={assetUrl(assetId) ?? undefined} alt="已上传的菜品照片" />
            ) : (
              <div className="upload-placeholder">
                <span className="upload-placeholder__mark" aria-hidden="true">＋</span>
                <strong>{copy.uploadLabel}</strong>
                <small>{copy.uploadHint}</small>
              </div>
            )}
            <label className="btn btn-secondary upload-action" htmlFor="dishPhoto">
              {busy ? copy.uploading : assetId ? "更换照片" : copy.selectImage}
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
              <p className="eyebrow">01 / CHOOSE A PATH</p>
              <h2>你想怎么做？</h2>
            </div>
            <span className="field-counter">{assetId ? "SOURCE READY" : "WAITING FOR PHOTO"}</span>
          </div>
          <div className="mode-choice-row" role="group" aria-label="mode">
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
                <small>让 Gus 给出一份完整判断</small>
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
                <small>自己填写料理的关键字段</small>
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
            <label htmlFor="contextText">补充说明（可选）</label>
            <textarea
              id="contextText"
              value={contextText}
              maxLength={500}
              placeholder="例如：这是一道冬日里常做的汤……"
              onChange={(event) => setContextText(event.target.value)}
            />
            <span className="field-counter">{contextText.length} / 500</span>
          </div>

          {error && <div className="status-banner status-error">{error}</div>}
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
