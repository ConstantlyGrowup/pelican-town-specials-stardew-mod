import { useQueries, useQuery } from "@tanstack/react-query";
import { useSyncExternalStore, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { apiClient, assetUrl } from "../../api/client";
import { DownloadableImage } from "../../components/DownloadableImage";
import { DishSlot } from "../../components/ui/DishSlot";
import { GameUiIcon } from "../../components/ui/GameAssetIcon";
import type { components } from "../../api/generated/schema";
import { PRODUCT_COPY } from "../../i18n/copy";
import {
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
  const copy = PRODUCT_COPY.zh;
  const navigate = useNavigate();
  const [activeDishId, setActiveDishId] = useState<string | null>(null);
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

  return (
    <main className="cookbook-page">
      <section className="paper-panel cookbook-heading">
        <div className="cookbook-heading__icon" aria-hidden="true">
          <GameUiIcon name="collections" size={38} />
        </div>
        <div>
          <p className="eyebrow">ARCHIVE / DISH COLLECTION</p>
          <h1>{copy.cookbookTitle}</h1>
          <p>这里保存着已经正式写进菜单的菜品。</p>
        </div>
        <div className="collection-count" aria-label="收集品统计">
          <span>★ 已收集 {query.data?.length ?? 0} 道</span>
          <span>● 已选 {selectedIds.size} 道</span>
        </div>
      </section>

      {query.isLoading && <p className="status-banner status-info">{copy.loading}</p>}
      {query.isError && (
        <div className="status-banner status-error">{copy.cookbookLoadFailed}</div>
      )}
      {query.data && query.data.length === 0 && (
        <div className="empty-state">
          <p>{copy.cookbookEmpty}</p>
          <Link className="btn btn-primary" to="/create">开始创建</Link>
        </div>
      )}

      <div className="cookbook-layout">
        <section className="paper-panel cookbook-grid-panel" aria-labelledby="collection-grid-title">
          <div className="panel-section-heading">
            <div>
              <p className="eyebrow">SAVED RECIPES</p>
              <h2 id="collection-grid-title">已保存菜品</h2>
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

        <aside className="paper-panel detail-panel cookbook-feature" aria-label="收集品预览">
          <p className="eyebrow">SELECTED RECIPE / PREVIEW</p>
          {activeDish ? (
            <>
              {activeDetail?.visuals.previewAssetId ? (
                <div className="detail-preview">
                  <DownloadableImage
                    src={assetUrl(activeDetail.visuals.previewAssetId) ?? ""}
                    alt={`${activeDish.displayName}预览`}
                    downloadName={`${activeDish.displayName}-预览`}
                  />
                </div>
              ) : (
                <div className="detail-preview detail-preview-placeholder">
                  <GameUiIcon name="dish" size={64} alt="料理图标" />
                  <small>
                    {activeDetailLoading ? "正在读取这道菜的预览…" : "这道菜还没有预览图"}
                  </small>
                </div>
              )}
              <div className="detail-title-row">
                <div>
                  <p className="detail-display-name">{activeDish.displayName}</p>
                  <span className="tag-chip">分类 / {activeDish.categoryLabel}</span>
                </div>
                <span className="detail-badge">ARCHIVED</span>
              </div>
              <p>{activeDish.description}</p>
              {(activeDish.tags ?? []).length > 0 && (
                <div className="tag-row">
                  {activeDish.tags?.map((tag) => <span key={tag} className="tag-chip">{tag}</span>)}
                </div>
              )}
              <Link className="btn btn-secondary" to={`/cookbook/${activeDish.dishId}`}>
                查看完整菜品 →
              </Link>
            </>
          ) : (
            <div className="empty-state">选择一个菜品查看详细信息。</div>
          )}
        </aside>
      </div>

      <div className="pack-bar">
        <div>
          <strong>已选择 {selectedIds.size} 道菜</strong>
          <span className="pack-bar__hint">把这些菜整理成菜单，带进游戏。</span>
        </div>
        <button
          className="btn btn-primary"
          type="button"
          disabled={selectedIds.size === 0}
          onClick={() => navigate("/pack-menu")}
          aria-label={copy.packMenu}
        >
          {copy.packMenu} →
        </button>
      </div>
    </main>
  );
}
