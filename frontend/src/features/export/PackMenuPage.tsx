import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { apiClient } from "../../api/client";
import type { components } from "../../api/generated/schema";
import { PRODUCT_COPY } from "../../i18n/copy";
import { getSelectedDishIds } from "../cookbook/selectionStore";
import { ValidationIssues } from "./ValidationIssues";

type CookbookDishDetail = components["schemas"]["CookbookDishDetail"];
type ExportSpec = components["schemas"]["ExportSpec"];
type ValidationReport = components["schemas"]["ValidationReport"];

function newIdempotencyKey(): string {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) {
    return crypto.randomUUID();
  }
  return `export-${Date.now()}-${Math.random().toString(36).slice(2)}`;
}

export function PackMenuPage() {
  const copy = PRODUCT_COPY.zh;
  const navigate = useNavigate();
  const [selectedIds] = useState<string[]>(() => [...getSelectedDishIds()]);

  const [packDisplayName, setPackDisplayName] = useState("家庭菜单");
  const [packSlug, setPackSlug] = useState("FamilyMenu");
  const [version, setVersion] = useState("1.0.0");
  const [description, setDescription] = useState("一份装满鹈鹕镇风味的菜单。");
  const [report, setReport] = useState<ValidationReport | null>(null);
  const [validating, setValidating] = useState(false);
  const [packing, setPacking] = useState(false);
  const [confirmWarnings, setConfirmWarnings] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);

  const dishesQuery = useQuery({
    queryKey: ["export-dishes", selectedIds],
    queryFn: async (): Promise<CookbookDishDetail[]> => {
      const details = await Promise.all(
        selectedIds.map(async (dishId) => {
          const { data, error } = await apiClient.GET("/api/v1/cookbook/{dish_id}", {
            params: { path: { dish_id: dishId } },
          });
          if (error || !data) {
            throw new Error("load failed");
          }
          return data;
        }),
      );
      return details;
    },
    enabled: selectedIds.length > 0,
  });

  const issues = report?.issues ?? [];
  const hasErrors = issues.some((issue) => issue.severity === "ERROR");
  const hasWarnings = issues.some((issue) => issue.severity === "WARNING");
  const canPack =
    report !== null &&
    !hasErrors &&
    (!hasWarnings || confirmWarnings) &&
    !packing &&
    !dishesQuery.isLoading;

  const spec: ExportSpec = {
    dishIds: selectedIds,
    packDisplayName,
    packSlug,
    version,
    description,
    language: "zh-CN",
  };

  async function onValidate() {
    setValidating(true);
    setFormError(null);
    const { data, error } = await apiClient.POST("/api/v1/exports/validate", {
      body: spec,
    });
    setValidating(false);
    if (error || !data) {
      setFormError(copy.validateFailed);
      return;
    }
    setReport(data);
  }

  async function onPack() {
    if (!canPack) {
      return;
    }
    setPacking(true);
    setFormError(null);
    const { data, error } = await apiClient.POST("/api/v1/exports", {
      body: spec,
      params: { header: { "Idempotency-Key": newIdempotencyKey() } },
    });
    setPacking(false);
    if (error || !data) {
      setFormError(copy.packFailed);
      return;
    }
    navigate(`/bring-in-game/${data.exportId}`);
  }

  if (selectedIds.length === 0) {
    return (
      <main>
        <h1>{copy.packMenuTitle}</h1>
        <div className="status-banner status-warning">{copy.noDishesSelected}</div>
        <Link to="/cookbook" className="btn">
          {copy.backToCookbook}
        </Link>
      </main>
    );
  }

  return (
    <main>
      <h1>{copy.packMenuTitle}</h1>
      <p>{copy.packMenuSubtitle}</p>

      <section className="card">
        <h2>{copy.selectedDishes}</h2>
        {dishesQuery.isLoading && <p>{copy.loading}</p>}
        {dishesQuery.isError && (
          <div className="status-banner status-error">{copy.cookbookLoadFailed}</div>
        )}
        <ul style={{ listStyle: "none", padding: 0 }}>
          {dishesQuery.data?.map((dish) => (
            <li key={dish.dishId} className="selected-dish">
              <strong>{dish.displayName}</strong>
              <span>{dish.categoryLabel}</span>
            </li>
          ))}
        </ul>
      </section>

      <section className="card">
        <div className="field">
          <label htmlFor="packDisplayName">{copy.packDisplayNameLabel}</label>
          <input
            id="packDisplayName"
            value={packDisplayName}
            maxLength={80}
            onChange={(event) => setPackDisplayName(event.target.value)}
          />
        </div>
        <div className="field">
          <label htmlFor="packSlug">{copy.packSlugLabel}</label>
          <input
            id="packSlug"
            value={packSlug}
            maxLength={48}
            onChange={(event) => setPackSlug(event.target.value)}
          />
          <p className="error">{copy.packSlugHint}</p>
        </div>
        <div className="field">
          <label htmlFor="version">{copy.versionLabel}</label>
          <input
            id="version"
            value={version}
            maxLength={32}
            onChange={(event) => setVersion(event.target.value)}
          />
        </div>
        <div className="field">
          <label htmlFor="description">{copy.descriptionLabel}</label>
          <textarea
            id="description"
            value={description}
            maxLength={200}
            onChange={(event) => setDescription(event.target.value)}
          />
        </div>

        {formError && <div className="status-banner status-error">{formError}</div>}

        <button
          className="btn"
          type="button"
          onClick={onValidate}
          disabled={validating || dishesQuery.isLoading}
        >
          {validating ? copy.validating : copy.validateButton}
        </button>

        {report && (
          <>
            <ValidationIssues issues={issues} />
            {hasErrors && (
              <div className="status-banner status-error">{copy.validationHasErrors}</div>
            )}
            {!hasErrors && !hasWarnings && (
              <div className="status-banner status-success">{copy.validationPassed}</div>
            )}
            {hasWarnings && (
              <>
                <div className="status-banner status-warning">
                  {copy.validationHasWarnings}
                </div>
                <label className="warning-confirm">
                  <input
                    type="checkbox"
                    checked={confirmWarnings}
                    onChange={(event) => setConfirmWarnings(event.target.checked)}
                  />
                  {copy.confirmWarnings}
                </label>
              </>
            )}
          </>
        )}

        <button
          className="btn btn-primary"
          type="button"
          onClick={onPack}
          disabled={!canPack}
        >
          {packing ? copy.packing : copy.packButton}
        </button>
      </section>
    </main>
  );
}
