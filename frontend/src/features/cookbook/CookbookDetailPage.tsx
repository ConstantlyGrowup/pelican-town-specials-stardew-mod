import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { apiClient, assetUrl } from "../../api/client";
import { DownloadableImage } from "../../components/DownloadableImage";
import { GameObjectIcon, GameUiIcon, SpecificIcon } from "../../components/ui/GameAssetIcon";
import { PixelModal } from "../../components/ui/PixelModal";
import type { components } from "../../api/generated/schema";
import { useCopy } from "../../i18n/locale";
import { clearSelectionFor } from "./selectionStore";

type CookbookDishDetail = components["schemas"]["CookbookDishDetail"];

export function CookbookDetailPage() {
  const { dishId } = useParams<{ dishId: string }>();
  const copy = useCopy();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [confirming, setConfirming] = useState(false);
  const [deleting, setDeleting] = useState(false);
  // The transient delete error stores a catalog key so a live message
  // re-localizes when the user switches the UI language (M7-T25-I18N-001).
  const [error, setError] = useState<"deleteFailed" | null>(null);

  const query = useQuery({
    queryKey: ["cookbook", dishId],
    queryFn: async (): Promise<CookbookDishDetail> => {
      const { data, error: loadError } = await apiClient.GET(
        "/api/v1/cookbook/{dish_id}",
        { params: { path: { dish_id: dishId ?? "" } } },
      );
      if (loadError || !data) {
        throw new Error("load failed");
      }
      return data;
    },
    enabled: Boolean(dishId),
  });

  async function onConfirmDelete() {
    if (!dishId) {
      return;
    }
    setDeleting(true);
    setError(null);
    const { error: deleteError } = await apiClient.DELETE("/api/v1/cookbook/{dish_id}", {
      params: { path: { dish_id: dishId } },
    });
    setDeleting(false);
    if (deleteError) {
      setError("deleteFailed");
      return;
    }
    clearSelectionFor(dishId);
    await queryClient.invalidateQueries({ queryKey: ["cookbook"] });
    navigate("/cookbook");
  }

  if (query.isLoading) {
    return (
      <main className="cookbook-detail-page">
        <h1>{copy.cookbookTitle}</h1>
        <p className="status-banner status-info">{copy.loading}</p>
      </main>
    );
  }

  if (query.isError || !query.data) {
    return (
      <main className="cookbook-detail-page">
        <h1>{copy.unknownDish}</h1>
        <p className="page-subtitle">
          <Link to="/cookbook">{copy.backToList}</Link>
        </p>
      </main>
    );
  }

  const dish = query.data;
  const previewUrl = assetUrl(dish.visuals.previewAssetId);
  const iconUrl = assetUrl(dish.visuals.icon16AssetId);

  return (
    <main className="cookbook-detail-page">
      <div className="page-header">
        <div>
          <Link className="back-link" to="/cookbook">← {copy.backToList}</Link>
          <p className="eyebrow">{copy.eyebrowArchivedDish}</p>
          <h1>{dish.displayName}</h1>
          <p className="page-subtitle">{dish.categoryLabel} · {dish.internalName}</p>
        </div>
        <span className="detail-badge">{copy.draftStatusLabels.ARCHIVED}</span>
      </div>

      <div className="detail-layout">
        <section className="paper-panel detail-visual-panel" aria-label={copy.previewResourceAria.replace("{name}", dish.displayName)}>
          {previewUrl ? (
            <div className="detail-preview">
              <DownloadableImage
                src={previewUrl}
                alt={copy.previewImageAlt.replace("{name}", dish.displayName)}
                downloadName={`${dish.displayName}${copy.previewDownloadSuffix}`}
                style={{ maxWidth: "100%", height: "auto", display: "block" }}
              />
            </div>
          ) : (
            <div className="detail-preview detail-preview-placeholder" aria-label={copy.noPreviewPlaceholder}>
              <span aria-hidden="true">✣</span>
            </div>
          )}
          {iconUrl && (
            <div className="detail-icon-row">
              <img
                src={iconUrl}
                alt={copy.iconImageAlt.replace("{name}", dish.displayName)}
                width={64}
                height={64}
                style={{ imageRendering: "pixelated", display: "block" }}
              />
              <span>{copy.iconMeta16}</span>
            </div>
          )}
        </section>

        <article className="paper-panel detail-info-panel">
          <div className="detail-title-row">
            <div>
              <p className="eyebrow">{copy.eyebrowDishCard}</p>
              <p className="detail-display-name">{dish.displayName}</p>
            </div>
            <span className="tag-chip">{dish.categoryLabel}</span>
          </div>
          <p className="detail-description">{dish.description}</p>
          {(dish.tags ?? []).length > 0 && (
            <div className="tag-row">
              {dish.tags?.map((tag) => <span key={tag} className="tag-chip">{tag}</span>)}
            </div>
          )}

          <section className="detail-stats" aria-labelledby="dish-stats-title">
            <h3 id="dish-stats-title">
              <GameUiIcon name="dish" size={28} />
              {copy.statsTitle}
            </h3>
            <div className="stat-grid">
              <div className="stat-row">
                <span className="stat-row__label">
                  <GameUiIcon name="energy" size={24} />
                  {copy.edibilityLabel}
                </span>
                <strong>{dish.gameplay.recovery.edibility}</strong>
              </div>
              <div className="stat-row">
                <span className="stat-row__label">
                  <SpecificIcon name="sellPrice" size={28} />
                  {copy.sellPriceLabel}
                </span>
                <strong>{dish.gameplay.sellPrice} g</strong>
              </div>
              <div className="stat-row">
                <span className="stat-row__label">
                  <SpecificIcon name="edibility" size={28} />
                  {copy.energyLabel}
                </span>
                <strong>{dish.gameplay.recovery.energyRestore}</strong>
              </div>
              <div className="stat-row">
                <span className="stat-row__label">
                  <SpecificIcon name="health" size={28} />
                  {copy.healthLabel}
                </span>
                <strong>{dish.gameplay.recovery.healthRestore}</strong>
              </div>
            </div>
          </section>

          <section className="detail-ingredients" aria-labelledby="ingredients-title">
            <h3 id="ingredients-title">{copy.ingredientsLabel}</h3>
            <ul className="ingredient-list">
              {dish.gameplay.ingredients.map((ingredient) => (
                <li key={ingredient.itemId} className="ingredient-row">
                  <span className="ingredient-row__content">
                    <GameObjectIcon itemId={ingredient.itemId} size={40} />
                    <span>{ingredient.displayName} × {ingredient.quantity}</span>
                  </span>
                </li>
              ))}
            </ul>
          </section>
        </article>
      </div>

      {error && <div className="status-banner status-error">{copy[error]}</div>}
      {!confirming && (
        <div className="detail-footer">
          <button className="btn btn-danger" type="button" onClick={() => setConfirming(true)}>
            {copy.deleteDish}
          </button>
        </div>
      )}
      {confirming && (
        <PixelModal
          title={copy.deleteConfirmTitle}
          description={copy.deleteConfirmMessage}
          onClose={() => setConfirming(false)}
          footer={
            <>
              <button
                className="btn btn-danger"
                type="button"
                onClick={onConfirmDelete}
                disabled={deleting}
              >
                {copy.confirmDelete}
              </button>
              <button className="btn" type="button" onClick={() => setConfirming(false)}>
                {copy.cancelDelete}
              </button>
            </>
          }
        >
          <p>{copy.deleteDishMessage}</p>
        </PixelModal>
      )}
    </main>
  );
}
