import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { useForm, useFormState } from "react-hook-form";
import { useNavigate, useParams } from "react-router-dom";
import { apiClient, assetUrl, getCsrfToken } from "../../api/client";
import { DownloadableImage } from "../../components/DownloadableImage";
import type { components } from "../../api/generated/schema";
import { PRODUCT_COPY } from "../../i18n/copy";
import {
  fromDraftView,
  toPatchInput,
  type BlueprintFormValues,
  type BlueprintIngredientRow,
} from "./blueprintForm";
import {
  CategoryPickerModal,
  IngredientPickerModal,
  TagPickerModal,
} from "./pickers";
import { GenerationError } from "../generation/GenerationError";
import { GenerationProgress } from "../generation/GenerationProgress";
import { useGeneration } from "../generation/useGeneration";

type DraftView = components["schemas"]["DraftView"];
type IngredientCatalogItemView = components["schemas"]["IngredientCatalogItemView"];

export function BlueprintEditorPage() {
  const { draftId } = useParams<{ draftId: string }>();
  const copy = PRODUCT_COPY.zh;
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [ingredients, setIngredients] = useState<BlueprintIngredientRow[]>([]);
  const [categoryPickerOpen, setCategoryPickerOpen] = useState(false);
  const [tagPickerOpen, setTagPickerOpen] = useState(false);
  const [ingredientPickerOpen, setIngredientPickerOpen] = useState(false);
  const [conflict, setConflict] = useState(false);
  const [stale, setStale] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

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
      setStale(false);
      void queryClient.invalidateQueries({ queryKey: ["draft", draftId] });
    },
  });

  const form = useForm<BlueprintFormValues>({
    defaultValues: {
      displayName: "",
      internalName: "",
      categoryLabel: "",
      description: "",
      tags: "",
      ingredients: [],
      edibility: 0,
      sellPrice: 0,
      isDrink: false,
    },
  });
  const { setError, clearErrors } = form;
  const formState = useFormState({ control: form.control });

  useEffect(() => {
    if (!query.data) {
      return;
    }
    const values = fromDraftView(query.data);
    form.reset(values);
    setIngredients(values.ingredients);
  }, [query.data?.draftId, query.data?.revision, form]);

  function addIngredient(
    item: IngredientCatalogItemView,
    catalogVersion: string,
  ) {
    if (ingredients.length >= 8) {
      return;
    }
    if (ingredients.some((ingredient) => ingredient.itemId === item.itemId)) {
      return;
    }
    setIngredients((current) => [
      ...current,
      {
        itemId: item.itemId,
        displayName: item.displayNameZh || item.displayNameEn,
        quantity: 1,
        mappingReason: "catalog selection",
        catalogVersion: catalogVersion,
      },
    ]);
  }

  function updateQuantity(itemId: string, quantity: number) {
    setIngredients((current) =>
      current.map((ingredient) =>
        ingredient.itemId === itemId
          ? { ...ingredient, quantity: Math.max(1, Math.min(99, quantity)) }
          : ingredient,
      ),
    );
  }

  function removeIngredient(itemId: string) {
    setIngredients((current) =>
      current.filter((ingredient) => ingredient.itemId !== itemId),
    );
  }

  function toggleTag(value: string) {
    const current = (form.getValues("tags") ?? "")
      .split(",")
      .map((tag) => tag.trim())
      .filter(Boolean);
    const next = current.includes(value)
      ? current.filter((tag) => tag !== value)
      : [...current, value];
    form.setValue("tags", next.join(","), { shouldDirty: true });
  }

  const categoryLabel = form.watch("categoryLabel");
  const tagList = (form.watch("tags") ?? "")
    .split(",")
    .map((tag) => tag.trim())
    .filter(Boolean);

  function validateBlueprint(values: BlueprintFormValues): boolean {
    clearErrors();
    let valid = true;
    if (!values.displayName.trim()) {
      setError("displayName", { type: "manual", message: copy.requiredField });
      valid = false;
    }
    if (!/^[A-Za-z][A-Za-z0-9_]{2,47}$/.test(values.internalName)) {
      setError("internalName", {
        type: "manual",
        message: copy.internalNameFormatError,
      });
      valid = false;
    }
    if (!values.categoryLabel.trim()) {
      setError("categoryLabel", { type: "manual", message: copy.requiredField });
      valid = false;
    }
    if (!values.description.trim()) {
      setError("description", {
        type: "manual",
        message: copy.descriptionRequiredError,
      });
      valid = false;
    }
    return valid;
  }

  async function onSave() {
    if (!query.data) {
      return;
    }
    const values = form.getValues();
    if (!validateBlueprint(values)) {
      return;
    }
    const input = toPatchInput({ ...values, ingredients });
    setBusy(true);
    setActionError(null);
    setConflict(false);
    setStale(false);
    const { data, error, response } = await apiClient.PATCH(
      "/api/v1/drafts/{draft_id}",
      {
        params: { path: { draft_id: draftId ?? "" } },
        body: {
          expectedRevision: query.data.revision,
          presentation: input.presentation,
          gameplay: input.gameplay,
        },
      },
    );
    setBusy(false);
    if (response.status === 409) {
      setConflict(true);
      return;
    }
    if (error || !data) {
      setActionError(copy.saveFailed);
      return;
    }
    queryClient.setQueryData(["draft", draftId], data);
    form.reset(fromDraftView(data));
    setIngredients(fromDraftView(data).ingredients);
    if (data.status === "STALE_PREVIEW") {
      setStale(true);
    }
  }

  async function onRefreshDraft() {
    await queryClient.invalidateQueries({ queryKey: ["draft", draftId] });
    setConflict(false);
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
      setActionError(copy.discardDraftFailed);
      return;
    }
    navigate("/");
  }

  if (query.isLoading) {
    return (
      <main>
        <h1>{copy.draftTitle}</h1>
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

  if (draft.mode !== "BLUEPRINT") {
    return (
      <main>
        <h1>{copy.draftNotFound}</h1>
      </main>
    );
  }

  const previewStale = stale || draft.status === "STALE_PREVIEW";
  const canGenerate =
    previewStale ||
    draft.status === "DRAFT" ||
    draft.status === "READY" ||
    draft.status === "FAILED";
  // A REVIEWABLE blueprint has no supported generation action (it must be
  // edited into STALE_PREVIEW first), so it must never expose a retry entry.
  const canRetry = canGenerate;
  const generationLabel = previewStale
    ? copy.updatePreview
    : draft.status === "FAILED"
      ? copy.retryGeneration
      : copy.generatePreview;
  const generationStreamingLabel = previewStale
    ? copy.updatingPreview
    : copy.generatingPreview;
  const generationHint = previewStale
    ? copy.updatePreviewHint
    : copy.generatePreviewHint;
  const previewUrl = assetUrl(draft.visuals?.previewAssetId);
  const iconUrl = assetUrl(draft.visuals?.icon16AssetId);

  return (
    <main>
      <h1>{copy.editingBlueprint}</h1>
      <p>
        {copy.statusLabel}：{draft.status}；{copy.revisionLabel}：{draft.revision}
      </p>
      {conflict && (
        <div className="status-banner status-error">
          <h2>{copy.revisionConflictTitle}</h2>
          <p>{copy.revisionConflictMessage}</p>
          <button className="btn" type="button" onClick={onRefreshDraft}>
            {copy.refreshDraft}
          </button>
        </div>
      )}
      {previewStale && (
        <div className="status-banner status-warning">
          <h2>{copy.stalePreviewTitle}</h2>
          <p>{copy.stalePreviewMessage}</p>
        </div>
      )}
      {(previewUrl || iconUrl) && (
        <section className="card" aria-label={`${draft.presentation?.displayName ?? copy.draftTitle}预览资源`}>
          {previewUrl && (
            <DownloadableImage
              src={previewUrl}
              alt={`${draft.presentation?.displayName ?? copy.draftTitle}预览`}
              downloadName={`${draft.presentation?.displayName ?? copy.draftTitle}-预览`}
              style={{ maxWidth: "100%", height: "auto", display: "block" }}
            />
          )}
          {iconUrl && (
            <img
              src={iconUrl}
              alt={`${draft.presentation?.displayName ?? copy.draftTitle}像素图标`}
              width={32}
              height={32}
              style={{ imageRendering: "pixelated", display: "block" }}
            />
          )}
        </section>
      )}
      {generation.phase === "streaming" && (
        <GenerationProgress
          currentStage={generation.currentStage}
          succeededStages={generation.succeededStages}
          totalStages={generation.totalStages}
          preparingLabel={copy.updatingPreview}
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
      {canGenerate && (
        <div className="card">
          <p>{generationHint}</p>
          <button
            className="btn btn-primary"
            type="button"
            onClick={generation.begin}
            disabled={generation.phase === "streaming" || busy}
          >
            {generation.phase === "streaming"
              ? generationStreamingLabel
              : generationLabel}
          </button>
        </div>
      )}

      <form
        onSubmit={(event) => {
          event.preventDefault();
          void onSave();
        }}
        className="card"
      >
        <div className="field">
          <label htmlFor="displayName">{copy.displayNameLabel}</label>
          <input id="displayName" {...form.register("displayName")} />
          {formState.errors.displayName && (
            <span className="error" role="alert">
              {formState.errors.displayName.message}
            </span>
          )}
        </div>
        <div className="field">
          <label htmlFor="internalName">{copy.internalNameLabel}</label>
          <input id="internalName" {...form.register("internalName")} />
          <span className="hint">{copy.internalNameHint}</span>
          {formState.errors.internalName && (
            <span className="error" role="alert">
              {formState.errors.internalName.message}
            </span>
          )}
        </div>
        <div className="field">
          <label htmlFor="categoryLabel">{copy.categoryLabel}</label>
          <div>
            <span id="categoryLabel" className="picker-value">
              {categoryLabel || "—"}
            </span>
            <button
              className="btn"
              type="button"
              onClick={() => setCategoryPickerOpen(true)}
            >
              {copy.pickCategory}
            </button>
          </div>
          {formState.errors.categoryLabel && (
            <span className="error" role="alert">
              {formState.errors.categoryLabel.message}
            </span>
          )}
        </div>
        <div className="field">
          <label htmlFor="description">{copy.descriptionLabel}</label>
          <textarea id="description" {...form.register("description")} />
          <span className="hint">{copy.descriptionHint}</span>
          {formState.errors.description && (
            <span className="error" role="alert">
              {formState.errors.description.message}
            </span>
          )}
        </div>
        <div className="field">
          <label htmlFor="tags">{copy.tagsLabel}</label>
          <div>
            <span id="tags" className="picker-value">
              {tagList.join("、") || "—"}
            </span>
            <button
              className="btn"
              type="button"
              onClick={() => setTagPickerOpen(true)}
            >
              {copy.pickTags}
            </button>
          </div>
        </div>

        <div className="field">
          <label>{copy.ingredientsLabel}</label>
          <button
            className="btn"
            type="button"
            onClick={() => setIngredientPickerOpen(true)}
          >
            {copy.pickIngredient}
          </button>
        </div>
        <ul>
          {ingredients.map((ingredient) => (
            <li key={ingredient.itemId}>
              {ingredient.displayName}（{ingredient.itemId}）
              <label>
                {copy.ingredientQuantityLabel}
                <input
                  type="number"
                  min={1}
                  max={99}
                  value={ingredient.quantity}
                  onChange={(event) =>
                    updateQuantity(ingredient.itemId, Number(event.target.value))
                  }
                />
              </label>
              <button className="btn" type="button" onClick={() => removeIngredient(ingredient.itemId)}>
                {copy.removeIngredient}
              </button>
            </li>
          ))}
        </ul>

        <div className="field">
          <label htmlFor="edibility">{copy.edibilityLabel}</label>
          <input id="edibility" type="number" {...form.register("edibility", { valueAsNumber: true })} />
        </div>
        <div className="field">
          <label htmlFor="sellPrice">{copy.sellPriceLabel}</label>
          <input id="sellPrice" type="number" {...form.register("sellPrice", { valueAsNumber: true })} />
        </div>
        <div className="field">
          <label htmlFor="isDrink">{copy.isDrinkLabel}</label>
          <input id="isDrink" type="checkbox" {...form.register("isDrink")} />
        </div>

        {actionError && <div className="status-banner status-error">{actionError}</div>}
        <button className="btn btn-primary" type="submit" disabled={busy}>
          {busy ? copy.saving : copy.saveDraft}
        </button>
      </form>

      {draft.status === "REVIEWABLE" && !previewStale && (
        <button
          className="btn btn-primary"
          type="button"
          onClick={onArchive}
          disabled={busy || generation.phase === "streaming"}
        >
          {copy.archiveDish}
        </button>
      )}
      {draft.status !== "ARCHIVED" && draft.status !== "DISCARDED" && (
        <button
          className="btn"
          type="button"
          onClick={onDiscard}
          disabled={busy || generation.phase === "streaming"}
        >
          {copy.discardDraft}
        </button>
      )}

      {categoryPickerOpen && (
        <CategoryPickerModal
          onPick={(value) => {
            form.setValue("categoryLabel", value, { shouldDirty: true });
            setCategoryPickerOpen(false);
          }}
          onClose={() => setCategoryPickerOpen(false)}
        />
      )}
      {tagPickerOpen && (
        <TagPickerModal
          onPick={(value) => toggleTag(value)}
          onClose={() => setTagPickerOpen(false)}
        />
      )}
      {ingredientPickerOpen && (
        <IngredientPickerModal
          onAdd={(item, catalogVersion) => addIngredient(item, catalogVersion)}
          onClose={() => setIngredientPickerOpen(false)}
        />
      )}
    </main>
  );
}
