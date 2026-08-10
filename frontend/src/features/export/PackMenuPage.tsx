import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { apiClient } from "../../api/client";
import type { components } from "../../api/generated/schema";
import { useCopy } from "../../i18n/locale";
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
  const copy = useCopy();
  const navigate = useNavigate();
  const [selectedIds] = useState<string[]>(() => [...getSelectedDishIds()]);

  const [packDisplayName, setPackDisplayName] = useState(copy.defaultPackDisplayName);
  const [packSlug, setPackSlug] = useState(copy.defaultPackSlug);
  const [version, setVersion] = useState("1.0.0");
  const [description, setDescription] = useState(copy.defaultPackDescription);
  const [report, setReport] = useState<ValidationReport | null>(null);
  const [validating, setValidating] = useState(false);
  const [packing, setPacking] = useState(false);
  const [confirmWarnings, setConfirmWarnings] = useState(false);
  // The transient form error stores a catalog key so a live message
  // re-localizes when the user switches the UI language (M7-T25-I18N-001).
  const [formError, setFormError] = useState<
    "validateFailed" | "packFailed" | null
  >(null);

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
      setFormError("validateFailed");
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
      setFormError("packFailed");
      return;
    }
    navigate(`/bring-in-game/${data.exportId}`);
  }

  if (selectedIds.length === 0) {
    return (
      <main className="pack-page">
        <div className="page-header">
          <div>
            <p className="eyebrow">{copy.eyebrowExportMenuBuilder}</p>
            <h1>{copy.packMenuTitle}</h1>
          </div>
        </div>
        <div className="status-banner status-warning">{copy.noDishesSelected}</div>
        <Link to="/cookbook" className="btn">
          {copy.backToCookbook}
        </Link>
      </main>
    );
  }

  return (
    <main className="pack-page">
      <div className="page-header">
        <div>
          <p className="eyebrow">{copy.eyebrowExportPackage}</p>
          <h1>{copy.packMenuTitle}</h1>
          <p className="page-subtitle">{copy.packMenuSubtitle}</p>
        </div>
        <span className="export-stamp">{copy.readyToValidateStamp}</span>
      </div>

      <div className="pack-layout">
        <section className="paper-panel pack-selection-panel">
          <div className="panel-section-heading">
            <div>
              <p className="eyebrow">{copy.eyebrowSelectedItems}</p>
              <h2>{copy.selectedDishes}</h2>
            </div>
            <span className="field-counter">
              {copy.itemsCountLabel.replace("{count}", String(selectedIds.length))}
            </span>
          </div>
          {dishesQuery.isLoading && <p className="status-banner status-info">{copy.loading}</p>}
          {dishesQuery.isError && (
            <div className="status-banner status-error">{copy.cookbookLoadFailed}</div>
          )}
          <ul className="selected-dish-list">
            {dishesQuery.data?.map((dish, index) => (
              <li key={dish.dishId} className="selected-dish">
                <span className="selected-dish__number">{String(index + 1).padStart(2, "0")}</span>
                <span>
                  <strong>{dish.displayName}</strong>
                  <small>{dish.categoryLabel}</small>
                </span>
                <span aria-hidden="true">✓</span>
              </li>
            ))}
          </ul>
          <Link className="btn btn-ghost" to="/cookbook">{copy.backToReselect}</Link>
        </section>

      <section className="paper-panel pack-form-panel">
        <div className="panel-section-heading">
          <div>
            <p className="eyebrow">{copy.eyebrowPackageIdentity}</p>
            <h2>{copy.packInfoTitle}</h2>
          </div>
          <span className="export-stamp">{copy.localExport}</span>
        </div>
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

        {formError && <div className="status-banner status-error">{copy[formError]}</div>}

        <div className="action-row pack-actions">
          <button
            className="btn"
            type="button"
            onClick={onValidate}
            disabled={validating || dishesQuery.isLoading}
          >
            {validating ? copy.validating : copy.validateButton}
          </button>
        </div>

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

        <div className="action-row pack-actions">
          <button
            className="btn btn-primary"
            type="button"
            onClick={onPack}
            disabled={!canPack}
            aria-label={packing ? copy.packing : copy.packButton}
          >
            {packing ? copy.packing : copy.packButton} →
          </button>
        </div>
      </section>
      </div>
    </main>
  );
}
