import { useQueries, useQuery, useQueryClient } from "@tanstack/react-query";
import { useSyncExternalStore, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { apiClient, assetUrl } from "../../api/client";
import { DownloadableImage } from "../../components/DownloadableImage";
import { DishSlot } from "../../components/ui/DishSlot";
import { PixelModal } from "../../components/ui/PixelModal";
import { GameUiIcon } from "../../components/ui/GameAssetIcon";
import type { components } from "../../api/generated/schema";
import { useCopy } from "../../i18n/locale";
import {
  clearSelectionFor,
  getSelectedDishIds,
  subscribeSelection,
  toggleSelection,
} from "./selectionStore";

type CookbookDishSummary = components["schemas"]["CookbookDishSummary"];
type CookbookDishDetail = components["schemas"]["CookbookDishDetail"];

async function loadCookbook(): Promise<CookbookDishSummary[]> {
  const { data, error } = await apiClient.GET("/api/v1/cookbook");
  if (error || !data) {
    throw new Error("load failed");
  }
  return data.items;
}

async function loadCookbookDish(dishId: string): Promise<CookbookDishDetail> {
  const { data, error } = await apiClient.GET("/api/v1/cookbook/{dish_id}", {
    params: { path: { dish_id: dishId } },
  });
  if (error || !data) {
    throw new Error("load failed");
  }
  return data;
}

export function CookbookPage() {
  const copy = useCopy();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [activeDishId, setActiveDishId] = useState<string | null>(null);
  const [batchConfirmOpen, setBatchConfirmOpen] = useState(false);
  const [batchBusy, setBatchBusy] = useState(false);
  const [batchError, setBatchError] = useState(false);
  const selectedIds = useSyncExternalStore(subscribeSelection, getSelectedDishIds);
  const query = useQuery({
    queryKey: ["cookbook"],
    queryFn: loadCookbook,
  });
  const detailQueries = useQueries({
    queries: (query.data ?? []).map((dish) => ({
      queryKey: ["cookbook", dish.dishId],
      queryFn: () => loadCookbookDish(dish.dishId),
      staleTime: 5 * 60 * 1000,
    })),
  });
  const detailById = new Map<string, CookbookDishDetail>();
  (query.data ?? []).forEach((dish, index) => {
    const detail = detailQueries[index]?.data;
    if (detail) {
      detailById.set(dish.dishId, detail);
    }
  });
  const activeDish =
    query.data?.find((dish) => dish.dishId === activeDishId) ?? query.data?.[0];
  const activeDetail = activeDish ? detailById.get(activeDish.dishId) : undefined;
  const activeDetailIndex = activeDish
    ? query.data?.findIndex((dish) => dish.dishId === activeDish.dishId) ?? -1
    : -1;
  const activeDetailLoading = activeDetailIndex >= 0 && Boolean(detailQueries[activeDetailIndex]?.isLoading);

  // The batch delete reuses the per-dish tombstone endpoint sequentially so
  // the cascade (visuals, source drafts) keeps its single-dish guarantees;
  // failures leave the remaining selection intact for a retry.
  async function onConfirmBatchDelete() {
    const ids = [...selectedIds];
    if (ids.length === 0) {
      return;
    }
    setBatchConfirmOpen(false);
    setBatchError(false);
    setBatchBusy(true);
    let failed = 0;
    for (const dishId of ids) {
      const { error } = await apiClient.DELETE("/api/v1/cookbook/{dish_id}", {
        params: { path: { dish_id: dishId } },
      });
      if (error) {
        failed += 1;
      } else {
        clearSelectionFor(dishId);
      }
    }
    await queryClient.invalidateQueries({ queryKey: ["cookbook"] });
    setBatchBusy(false);
    if (failed > 0) {
      setBatchError(true);
    }
  }

  return (
    <main className="cookbook-page">
      <section className="paper-panel cookbook-heading">
        <div className="cookbook-heading__icon" aria-hidden="true">
          <GameUiIcon name="collections" size={38} />
        </div>
        <div>
          <p className="eyebrow">{copy.eyebrowDishCollection}</p>
          <h1>{copy.cookbookTitle}</h1>
          <p>{copy.cookbookDescription}</p>
        </div>
        <div className="collection-count" aria-label={copy.collectionStatsLabel}>
          <span>{copy.collectedCount.replace("{count}", String(query.data?.length ?? 0))}</span>
          <span>{copy.selectedCount.replace("{count}", String(selectedIds.size))}</span>
        </div>
      </section>

      {query.isLoading && <p className="status-banner status-info">{copy.loading}</p>}
      {query.isError && (
        <div className="status-banner status-error">{copy.cookbookLoadFailed}</div>
      )}
      {query.data && query.data.length === 0 && (
        <div className="empty-state">
          <p>{copy.cookbookEmpty}</p>
          <Link className="btn btn-primary" to="/create">{copy.startCreating}</Link>
        </div>
      )}

      <div className="cookbook-layout">
        <section className="paper-panel cookbook-grid-panel" aria-labelledby="collection-grid-title">
          <div className="panel-section-heading">
            <div>
              <p className="eyebrow">{copy.eyebrowSavedRecipes}</p>
              <h2 id="collection-grid-title">{copy.savedRecipesTitle}</h2>
            </div>
          </div>
          <ul className="slot-grid" style={{ listStyle: "none", padding: 0 }}>
            {query.data?.map((dish) => (
              <li key={dish.dishId} className="cookbook-slot-item">
                <DishSlot
                  label={dish.displayName}
                  imageUrl={assetUrl(detailById.get(dish.dishId)?.visuals.icon16AssetId)}
                  meta={dish.categoryLabel}
                  selected={selectedIds.has(dish.dishId)}
                  active={activeDish?.dishId === dish.dishId}
                  onClick={() => setActiveDishId(dish.dishId)}
                />
                <label className="cookbook-select">
                  <input
                    type="checkbox"
                    checked={selectedIds.has(dish.dishId)}
                    onChange={() => toggleSelection(dish.dishId)}
                  />
                  <span>{selectedIds.has(dish.dishId) ? copy.selected : copy.select}</span>
                </label>
              </li>
            ))}
            {Array.from({ length: Math.max(0, 8 - (query.data?.length ?? 0)) }).map((_, index) => (
              <li key={`empty-${index}`}>
                <DishSlot label="" empty />
              </li>
            ))}
          </ul>
        </section>

        <aside className="paper-panel detail-panel cookbook-feature" aria-label={copy.previewLabel}>
          <p className="eyebrow">{copy.eyebrowSelectedPreview}</p>
          {activeDish ? (
            <>
              {activeDetail?.visuals.previewAssetId ? (
                <div className="detail-preview">
                  <DownloadableImage
                    src={assetUrl(activeDetail.visuals.previewAssetId) ?? ""}
                    alt={copy.previewImageAlt.replace("{name}", activeDish.displayName)}
                    downloadName={`${activeDish.displayName}${copy.previewDownloadSuffix}`}
                  />
                </div>
              ) : (
                <div className="detail-preview detail-preview-placeholder">
                  <GameUiIcon name="dish" size={64} alt={copy.dishIconAlt} />
                  <small>
                    {activeDetailLoading ? copy.loadingPreview : copy.noPreviewYet}
                  </small>
                </div>
              )}
              <div className="detail-title-row">
                <div>
                  <p className="detail-display-name">{activeDish.displayName}</p>
                  <span className="tag-chip">
                    {copy.categoryChipLabel.replace("{category}", activeDish.categoryLabel)}
                  </span>
                </div>
                <span className="detail-badge">{copy.draftStatusLabels.ARCHIVED}</span>
              </div>
              <p>{activeDish.description}</p>
              {(activeDish.tags ?? []).length > 0 && (
                <div className="tag-row">
                  {activeDish.tags?.map((tag) => <span key={tag} className="tag-chip">{tag}</span>)}
                </div>
              )}
              <Link className="btn btn-secondary" to={`/cookbook/${activeDish.dishId}`}>
                {copy.viewFullDish}
              </Link>
            </>
          ) : (
            <div className="empty-state">{copy.noDishSelected}</div>
          )}
        </aside>
      </div>

      {batchError && (
        <div className="status-banner status-error" role="alert">
          {copy.batchDeleteFailed}
        </div>
      )}

      <div className="pack-bar">
        <div>
          <strong>{copy.packBarCount.replace("{count}", String(selectedIds.size))}</strong>
          <span className="pack-bar__hint">{copy.packBarHint}</span>
        </div>
        <div className="pack-bar__actions">
          {selectedIds.size > 0 && (
            <button
              className="btn btn-danger"
              type="button"
              disabled={batchBusy}
              onClick={() => {
                setBatchError(false);
                setBatchConfirmOpen(true);
              }}
              aria-label={copy.batchDelete}
            >
              {copy.batchDelete}
            </button>
          )}
          <button
            className="btn btn-primary"
            type="button"
            disabled={selectedIds.size === 0 || batchBusy}
            onClick={() => navigate("/pack-menu")}
            aria-label={copy.packMenu}
          >
            {copy.packMenu} →
          </button>
        </div>
      </div>

      {batchConfirmOpen && (
        <PixelModal
          title={copy.batchDelete}
          onClose={() => setBatchConfirmOpen(false)}
          footer={
            <>
              <button
                className="btn btn-danger"
                type="button"
                disabled={batchBusy}
                onClick={() => void onConfirmBatchDelete()}
              >
                {copy.deleteDish}
              </button>
              <button
                className="btn"
                type="button"
                disabled={batchBusy}
                onClick={() => setBatchConfirmOpen(false)}
              >
                {copy.cancelDelete}
              </button>
            </>
          }
        >
          <p>
            {copy.batchDeleteMessage.replace("{count}", String(selectedIds.size))}
          </p>
        </PixelModal>
      )}
    </main>
  );
}
