import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { apiClient } from "../../api/client";
import { uploadImage } from "../../api/uploadImage";
import type { components } from "../../api/generated/schema";
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
    <main>
      <h1>{copy.createTitle}</h1>
      <section className="card">
        <div className="field">
          <label htmlFor="dishPhoto">{copy.uploadLabel}</label>
          <input
            id="dishPhoto"
            type="file"
            accept="image/png,image/jpeg,image/jpg,image/webp,.png,.jpg,.jpeg,.webp"
            onChange={onFileChange}
          />
          <p className="error">{copy.uploadHint}</p>
        </div>
        {assetId && <p role="status">{copy.uploadComplete}</p>}

        <div role="group" aria-label="mode">
          <button
            type="button"
            className="btn"
            aria-pressed={mode === "ASK_GUS"}
            onClick={() => setMode("ASK_GUS")}
          >
            {copy.createAskGus}
          </button>
          <button
            type="button"
            className="btn"
            aria-pressed={mode === "BLUEPRINT"}
            onClick={() => setMode("BLUEPRINT")}
          >
            {copy.createBlueprint}
          </button>
        </div>
        {mode === "BLUEPRINT" && (
          <p className="status-banner status-warning">{copy.blueprintFromOriginalOnly}</p>
        )}

        <div className="field">
          <label htmlFor="contextText">补充说明（可选）</label>
          <textarea
            id="contextText"
            value={contextText}
            maxLength={500}
            onChange={(event) => setContextText(event.target.value)}
          />
        </div>

        {error && <div className="status-banner status-error">{error}</div>}
        <button
          className="btn btn-primary"
          type="button"
          onClick={onCreate}
          disabled={!assetId || busy}
        >
          {busy ? copy.creating : copy.createDraft}
        </button>
      </section>
    </main>
  );
}
