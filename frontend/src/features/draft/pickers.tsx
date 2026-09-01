import { useEffect, useMemo, useState } from "react";
import { apiClient } from "../../api/client";
import { PixelModal } from "../../components/ui/PixelModal";
import type { components } from "../../api/generated/schema";
import { metaDisplayLabel } from "../../i18n/metaLabels";
import { useCopy, useLocale } from "../../i18n/locale";

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
  const copy = useCopy();
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
  const copy = useCopy();
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
  const copy = useCopy();
  return (
    <MetaPickerModal
      title={copy.pickCategory}
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
  const copy = useCopy();
  return (
    <MetaPickerModal
      title={copy.pickTags}
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
  const copy = useCopy();
  const locale = useLocale();
  const [query, setQuery] = useState("");
  const [offset, setOffset] = useState(0);
  const [items, setItems] = useState<MetaOption[]>([]);
  const [loading, setLoading] = useState(true);

  // The curated option lists are small, so they are fetched in full and
  // filtered locally: the backend can only match the canonical Chinese
  // values, while the visible labels follow the UI locale.
  useEffect(() => {
    let active = true;
    setLoading(true);
    void apiClient
      .GET(endpoint, { params: { query: { query: "", limit: 100, offset: 0 } } })
      .then(({ data, error }) => {
        if (!active) {
          return;
        }
        setLoading(false);
        if (!error && data) {
          setItems(data.items);
        }
      });
    return () => {
      active = false;
    };
  }, [endpoint]);

  const filtered = useMemo(() => {
    const normalized = query.trim().toLowerCase();
    if (!normalized) {
      return items;
    }
    return items.filter(
      (item) =>
        item.value.toLowerCase().includes(normalized) ||
        metaDisplayLabel(item.value, locale).toLowerCase().includes(normalized),
    );
  }, [items, query, locale]);
  const visible = filtered.slice(offset, offset + PAGE_SIZE);

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
      ) : filtered.length === 0 ? (
        <p>{copy.pickEmpty}</p>
      ) : (
        <ul className="picker-list">
          {visible.map((item) => (
            <li key={item.value}>
              <button
                className="btn picker-option"
                type="button"
                onClick={() => onPick(item.value)}
              >
                {metaDisplayLabel(item.value, locale)}
              </button>
            </li>
          ))}
        </ul>
      )}
      <Pager offset={offset} total={filtered.length} onOffset={setOffset} />
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
  const copy = useCopy();
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
                {copy.ingredientNameBoth
                  .replace("{zh}", item.displayNameZh)
                  .replace("{en}", item.displayNameEn)}
              </button>
            </li>
          ))}
        </ul>
      )}
      <Pager offset={offset} total={total} onOffset={setOffset} />
    </Modal>
  );
}
