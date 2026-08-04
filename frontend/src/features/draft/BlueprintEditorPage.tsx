import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { useForm } from "react-hook-form";
import { useNavigate, useParams } from "react-router-dom";
import { apiClient } from "../../api/client";
import type { components } from "../../api/generated/schema";
import { PRODUCT_COPY } from "../../i18n/copy";
import {
  fromDraftView,
  toPatchInput,
  type BlueprintFormValues,
  type BlueprintIngredientRow,
} from "./blueprintForm";

type DraftView = components["schemas"]["DraftView"];
type IngredientCatalogItemView = components["schemas"]["IngredientCatalogItemView"];

export function BlueprintEditorPage() {
  const { draftId } = useParams<{ draftId: string }>();
  const copy = PRODUCT_COPY.zh;
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [ingredients, setIngredients] = useState<BlueprintIngredientRow[]>([]);
  const [searchQuery, setSearchQuery] = useState("");
  const [searchResults, setSearchResults] = useState<IngredientCatalogItemView[]>([]);
  const [searchCatalogVersion, setSearchCatalogVersion] = useState("");
  const [conflict, setConflict] = useState(false);
  const [stale, setStale] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

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

  useEffect(() => {
    if (!query.data) {
      return;
    }
    const values = fromDraftView(query.data);
    form.reset(values);
    setIngredients(values.ingredients);
  }, [query.data?.draftId, query.data?.revision, form]);

  async function onSearch() {
    const trimmed = searchQuery.trim();
    if (!trimmed) {
      setSearchResults([]);
      return;
    }
    const { data, error } = await apiClient.GET("/api/v1/catalog/ingredients", {
      params: { query: { query: trimmed, limit: 20 } },
    });
    if (error || !data) {
      setSearchResults([]);
      return;
    }
    setSearchResults(data.items);
    setSearchCatalogVersion(data.catalogVersion);
  }

  function addIngredient(item: IngredientCatalogItemView) {
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
        catalogVersion: searchCatalogVersion,
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

  async function onSave() {
    if (!query.data) {
      return;
    }
    const values = form.getValues();
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

  async function onConvertToBlueprint() {
    setBusy(true);
    setActionError(null);
    const { data, error } = await apiClient.POST(
      "/api/v1/drafts/{draft_id}/convert-to-blueprint",
      { params: { path: { draft_id: draftId ?? "" } } },
    );
    setBusy(false);
    if (error || !data) {
      setActionError(copy.saveFailed);
      return;
    }
    navigate(`/drafts/${data.draftId}`);
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

  if (draft.mode === "ASK_GUS") {
    return (
      <main>
        <h1>{copy.draftTitle}</h1>
        <p className="status-banner status-warning">{copy.readOnlyAskGus}</p>
        <section className="card">
          <p>
            {copy.modeLabel}：{copy.askGus}；{copy.statusLabel}：{draft.status}；{copy.revisionLabel}：
            {draft.revision}
          </p>
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
        </section>
        {draft.status !== "ARCHIVED" && draft.status !== "DISCARDED" && (
          <>
            <p className="status-banner status-warning">{copy.convertHint}</p>
            <button className="btn" type="button" onClick={onConvertToBlueprint} disabled={busy}>
              {copy.convertToBlueprint}
            </button>
          </>
        )}
        {draft.status === "REVIEWABLE" && (
          <button className="btn btn-primary" type="button" onClick={onArchive} disabled={busy}>
            {copy.archiveDish}
          </button>
        )}
        {actionError && <div className="status-banner status-error">{actionError}</div>}
      </main>
    );
  }

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
      {stale && (
        <div className="status-banner status-warning">
          <h2>{copy.stalePreviewTitle}</h2>
          <p>{copy.stalePreviewMessage}</p>
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
        </div>
        <div className="field">
          <label htmlFor="internalName">{copy.internalNameLabel}</label>
          <input id="internalName" {...form.register("internalName")} />
        </div>
        <div className="field">
          <label htmlFor="categoryLabel">{copy.categoryLabel}</label>
          <input id="categoryLabel" {...form.register("categoryLabel")} />
        </div>
        <div className="field">
          <label htmlFor="description">{copy.descriptionLabel}</label>
          <textarea id="description" {...form.register("description")} />
        </div>
        <div className="field">
          <label htmlFor="tags">{copy.tagsLabel}</label>
          <input id="tags" {...form.register("tags")} />
        </div>

        <div className="field">
          <label>{copy.ingredientsLabel}</label>
          <div>
            <input
              aria-label={copy.ingredientSearchPlaceholder}
              value={searchQuery}
              onChange={(event) => setSearchQuery(event.target.value)}
              placeholder={copy.ingredientSearchPlaceholder}
            />
            <button className="btn" type="button" onClick={onSearch}>
              {copy.ingredientSearchPlaceholder}
            </button>
          </div>
          {searchResults.length > 0 && (
            <ul>
              {searchResults.map((item) => (
                <li key={item.itemId}>
                  {item.displayNameZh}（{item.displayNameEn}）
                  <button className="btn" type="button" onClick={() => addIngredient(item)}>
                    {copy.addIngredient}
                  </button>
                </li>
              ))}
            </ul>
          )}
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

      {draft.status === "REVIEWABLE" && !stale && (
        <button className="btn btn-primary" type="button" onClick={onArchive} disabled={busy}>
          {copy.archiveDish}
        </button>
      )}
    </main>
  );
}
