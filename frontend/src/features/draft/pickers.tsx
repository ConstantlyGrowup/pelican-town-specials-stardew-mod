import { useEffect, useState } from "react";
import { apiClient } from "../../api/client";
import { PixelModal } from "../../components/ui/PixelModal";
import type { components } from "../../api/generated/schema";
import { PRODUCT_COPY } from "../../i18n/copy";

type MetaOption = components["schemas"]["MetaOption"];
type IngredientCatalogItemView = components["schemas"]["IngredientCatalogItemView"];

const PAGE_SIZE = 20;

function Modal({
  title,
  onClose,
  children,
}: {
  title: string;
  onClose: () => void;
  children: React.ReactNode;
}) {
  const copy = PRODUCT_COPY.zh;
  return (
    <PixelModal
      title={title}
      onClose={onClose}
      footer={
        <button className="btn" type="button" onClick={onClose}>
          {copy.pickClose}
        </button>
      }
    >
      {children}
    </PixelModal>
  );
}

function Pager({
  offset,
  total,
  onOffset,
}: {
  offset: number;
  total: number;
  onOffset: (next: number) => void;
}) {
  const copy = PRODUCT_COPY.zh;
  const hasPrev = offset > 0;
  const hasNext = offset + PAGE_SIZE < total;
  return (
    <div className="pager">
      <button
        className="btn"
        type="button"
        disabled={!hasPrev}
        onClick={() => onOffset(Math.max(0, offset - PAGE_SIZE))}
      >
        {copy.pickPrev}
      </button>
      <span>
        {offset + 1}–{Math.min(offset + PAGE_SIZE, total)} / {total}
      </span>
      <button
        className="btn"
        type="button"
        disabled={!hasNext}
        onClick={() => onOffset(offset + PAGE_SIZE)}
      >
        {copy.pickNext}
      </button>
    </div>
  );
}

export function CategoryPickerModal({
  onPick,
  onClose,
}: {
  onPick: (value: string) => void;
  onClose: () => void;
}) {
  return (
    <MetaPickerModal
      title={PRODUCT_COPY.zh.pickCategory}
      endpoint="/api/v1/meta/categories"
      onPick={onPick}
      onClose={onClose}
    />
  );
}

export function TagPickerModal({
  onPick,
  onClose,
}: {
  onPick: (value: string) => void;
  onClose: () => void;
}) {
  return (
    <MetaPickerModal
      title={PRODUCT_COPY.zh.pickTags}
      endpoint="/api/v1/meta/tags"
      onPick={onPick}
      onClose={onClose}
    />
  );
}

function MetaPickerModal({
  title,
  endpoint,
  onPick,
  onClose,
}: {
  title: string;
  endpoint: "/api/v1/meta/categories" | "/api/v1/meta/tags";
  onPick: (value: string) => void;
  onClose: () => void;
}) {
  const copy = PRODUCT_COPY.zh;
  const [query, setQuery] = useState("");
  const [offset, setOffset] = useState(0);
  const [items, setItems] = useState<MetaOption[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let active = true;
    setLoading(true);
    void apiClient
      .GET(endpoint, { params: { query: { query, limit: PAGE_SIZE, offset } } })
      .then(({ data, error }) => {
        if (!active) {
          return;
        }
        setLoading(false);
        if (!error && data) {
          setItems(data.items);
          setTotal(data.total);
        }
      });
    return () => {
      active = false;
    };
  }, [endpoint, query, offset]);

  return (
    <Modal title={title} onClose={onClose}>
      <input
        aria-label={copy.pickSearch}
        value={query}
        placeholder={copy.pickSearch}
        onChange={(event) => {
          setQuery(event.target.value);
          setOffset(0);
        }}
      />
      {loading ? (
        <p>{copy.loading}</p>
      ) : items.length === 0 ? (
        <p>{copy.pickEmpty}</p>
      ) : (
        <ul className="picker-list">
          {items.map((item) => (
            <li key={item.value}>
              <button
                className="btn picker-option"
                type="button"
                onClick={() => onPick(item.value)}
              >
                {item.value}
              </button>
            </li>
          ))}
        </ul>
      )}
      <Pager offset={offset} total={total} onOffset={setOffset} />
    </Modal>
  );
}

export function IngredientPickerModal({
  onAdd,
  onClose,
}: {
  onAdd: (item: IngredientCatalogItemView, catalogVersion: string) => void;
  onClose: () => void;
}) {
  const copy = PRODUCT_COPY.zh;
  const [query, setQuery] = useState("");
  const [offset, setOffset] = useState(0);
  const [items, setItems] = useState<IngredientCatalogItemView[]>([]);
  const [catalogVersion, setCatalogVersion] = useState("");
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let active = true;
    setLoading(true);
    void apiClient
      .GET("/api/v1/catalog/ingredients", {
        params: { query: { query, limit: PAGE_SIZE, offset } },
      })
      .then(({ data, error }) => {
        if (!active) {
          return;
        }
        setLoading(false);
        if (!error && data) {
          setItems(data.items);
          setCatalogVersion(data.catalogVersion);
          setTotal(data.total);
        }
      });
    return () => {
      active = false;
    };
  }, [query, offset]);

  return (
    <Modal title={copy.pickIngredient} onClose={onClose}>
      <input
        aria-label={copy.pickSearch}
        value={query}
        placeholder={copy.ingredientSearchPlaceholder}
        onChange={(event) => {
          setQuery(event.target.value);
          setOffset(0);
        }}
      />
      {loading ? (
        <p>{copy.loading}</p>
      ) : items.length === 0 ? (
        <p>{copy.pickEmpty}</p>
      ) : (
        <ul className="picker-list">
          {items.map((item) => (
            <li key={item.itemId}>
              <button
                className="btn picker-option"
                type="button"
                onClick={() => onAdd(item, catalogVersion)}
              >
                {item.displayNameZh}（{item.displayNameEn}）
              </button>
            </li>
          ))}
        </ul>
      )}
      <Pager offset={offset} total={total} onOffset={setOffset} />
    </Modal>
  );
}
