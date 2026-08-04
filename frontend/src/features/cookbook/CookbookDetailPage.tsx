import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { apiClient } from "../../api/client";
import type { components } from "../../api/generated/schema";
import { PRODUCT_COPY } from "../../i18n/copy";
import { clearSelectionFor } from "./selectionStore";

type CookbookDishDetail = components["schemas"]["CookbookDishDetail"];

export function CookbookDetailPage() {
  const { dishId } = useParams<{ dishId: string }>();
  const copy = PRODUCT_COPY.zh;
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [confirming, setConfirming] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [error, setError] = useState<string | null>(null);

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
      setError(copy.deleteFailed);
      return;
    }
    clearSelectionFor(dishId);
    await queryClient.invalidateQueries({ queryKey: ["cookbook"] });
    navigate("/cookbook");
  }

  if (query.isLoading) {
    return (
      <main>
        <h1>{copy.cookbookTitle}</h1>
        <p>{copy.loading}</p>
      </main>
    );
  }

  if (query.isError || !query.data) {
    return (
      <main>
        <h1>{copy.unknownDish}</h1>
        <p>
          <Link to="/cookbook">{copy.backToList}</Link>
        </p>
      </main>
    );
  }

  const dish = query.data;

  return (
    <main>
      <p>
        <Link to="/cookbook">{copy.backToList}</Link>
      </p>
      <article className="card">
        <h1>{dish.displayName}</h1>
        <p>{dish.internalName}</p>
        <p>{dish.categoryLabel}</p>
        <p>{dish.description}</p>
        {(dish.tags ?? []).length > 0 && <p>{(dish.tags ?? []).join("、")}</p>}
        <h2>{copy.ingredientsLabel}</h2>
        <ul>
          {dish.gameplay.ingredients.map((ingredient) => (
            <li key={ingredient.itemId}>
              {ingredient.displayName} × {ingredient.quantity}
            </li>
          ))}
        </ul>
        <p>
          {copy.edibilityLabel}：{dish.gameplay.recovery.edibility}；{copy.sellPriceLabel}：
          {dish.gameplay.sellPrice}
        </p>
      </article>

      {error && <div className="status-banner status-error">{error}</div>}
      {confirming ? (
        <div className="card">
          <h2>{copy.deleteConfirmTitle}</h2>
          <p>{copy.deleteConfirmMessage}</p>
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
        </div>
      ) : (
        <button className="btn btn-danger" type="button" onClick={() => setConfirming(true)}>
          {copy.deleteDish}
        </button>
      )}
    </main>
  );
}
