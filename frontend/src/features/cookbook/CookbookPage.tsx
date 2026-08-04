import { useQuery } from "@tanstack/react-query";
import { useSyncExternalStore } from "react";
import { Link } from "react-router-dom";
import { apiClient } from "../../api/client";
import type { components } from "../../api/generated/schema";
import { PRODUCT_COPY } from "../../i18n/copy";
import {
  getSelectedDishIds,
  subscribeSelection,
  toggleSelection,
} from "./selectionStore";

type CookbookDishSummary = components["schemas"]["CookbookDishSummary"];

async function loadCookbook(): Promise<CookbookDishSummary[]> {
  const { data, error } = await apiClient.GET("/api/v1/cookbook");
  if (error || !data) {
    throw new Error("load failed");
  }
  return data.items;
}

export function CookbookPage() {
  const copy = PRODUCT_COPY.zh;
  const selectedIds = useSyncExternalStore(subscribeSelection, getSelectedDishIds);
  const query = useQuery({
    queryKey: ["cookbook"],
    queryFn: loadCookbook,
  });

  return (
    <main>
      <h1>{copy.cookbookTitle}</h1>
      {query.isLoading && <p>{copy.loading}</p>}
      {query.isError && (
        <div className="status-banner status-error">{copy.cookbookLoadFailed}</div>
      )}
      {query.data && query.data.length === 0 && <p>{copy.cookbookEmpty}</p>}
      <ul style={{ listStyle: "none", padding: 0 }}>
        {query.data?.map((dish) => (
          <li key={dish.dishId} className="card" style={{ marginBottom: 12 }}>
            <Link to={`/cookbook/${dish.dishId}`}>
              <h2>{dish.displayName}</h2>
            </Link>
            <p>{dish.categoryLabel}</p>
            <p>{dish.description}</p>
            {(dish.tags ?? []).length > 0 && <p>{(dish.tags ?? []).join("、")}</p>}
            <label>
              <input
                type="checkbox"
                checked={selectedIds.has(dish.dishId)}
                onChange={() => toggleSelection(dish.dishId)}
              />
              {selectedIds.has(dish.dishId) ? copy.selected : copy.select}
            </label>
          </li>
        ))}
      </ul>
    </main>
  );
}
