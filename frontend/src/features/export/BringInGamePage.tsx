import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { apiClient } from "../../api/client";
import type { components } from "../../api/generated/schema";
import { useCopy } from "../../i18n/locale";

type ExportRecordView = components["schemas"]["ExportRecordView"];

export function BringInGamePage() {
  const copy = useCopy();
  const { exportId } = useParams<{ exportId: string }>();
  // The transient folder error stores a catalog key so a live message
  // re-localizes when the user switches the UI language (M7-T25-I18N-001).
  const [folderError, setFolderError] = useState<"openFolderFailed" | null>(null);

  const query = useQuery({
    queryKey: ["export", exportId],
    queryFn: async (): Promise<ExportRecordView> => {
      const { data, error } = await apiClient.GET("/api/v1/exports/{export_id}", {
        params: { path: { export_id: exportId ?? "" } },
      });
      if (error || !data) {
        throw new Error("load failed");
      }
      return data;
    },
    enabled: Boolean(exportId),
  });

  async function onOpenFolder() {
    setFolderError(null);
    const { error } = await apiClient.POST("/api/v1/exports/{export_id}/open-folder", {
      params: { path: { export_id: exportId ?? "" } },
    });
    if (error) {
      setFolderError("openFolderFailed");
    }
  }

  function onDownload() {
    window.location.href = `/api/v1/exports/${exportId ?? ""}/download`;
  }

  if (query.isLoading) {
    return (
      <main className="bring-page">
        <h1>{copy.bringInGameTitle}</h1>
        <p className="status-banner status-info">{copy.loading}</p>
      </main>
    );
  }

  if (query.isError || !query.data) {
    return (
      <main className="bring-page">
        <h1>{copy.bringInGameTitle}</h1>
        <div className="status-banner status-error">{copy.exportRecordNotFound}</div>
        <Link to="/cookbook" className="btn">
          {copy.backToCookbook}
        </Link>
      </main>
    );
  }

  const record = query.data;
  const statusLabel = copy.exportStatusLabels[record.status] ?? record.status;

  return (
    <main className="bring-page">
      <div className="page-header">
        <div>
          <p className="eyebrow">{copy.eyebrowInstallPackage}</p>
          <h1>{copy.bringInGameTitle}</h1>
          <p className="page-subtitle">{copy.bringInGameSubtitle}</p>
        </div>
        <span className={`export-stamp ${record.status === "SUCCEEDED" ? "export-stamp-success" : ""}`}>
          {statusLabel}
        </span>
      </div>

      <section className="paper-panel bring-summary">
        <div>
          <p className="eyebrow">{copy.eyebrowPackageReady}</p>
          <h2>{record.spec.packDisplayName}</h2>
        </div>
        <p>
          {copy.versionLabel}: {record.spec.version} · {copy.packSlugLabel}:{" "}
          {record.spec.packSlug}
        </p>
        <p>
          {copy.statusLabel}: {statusLabel}
        </p>
        <p>{record.spec.description}</p>

        <div className="action-row">
          <button className="btn btn-primary" type="button" onClick={onDownload}>
            {copy.downloadZip}
          </button>
          <button className="btn" type="button" onClick={onOpenFolder}>
            {copy.openExportFolder}
          </button>
        </div>
        {folderError && <div className="status-banner status-error">{copy[folderError]}</div>}
      </section>

      <section className="paper-panel steps-panel" aria-labelledby="bring-steps-title">
        <div className="panel-section-heading">
          <div>
            <p className="eyebrow">{copy.eyebrowInstallChecklist}</p>
            <h2 id="bring-steps-title">{copy.installChecklistTitle}</h2>
          </div>
          <span className="field-counter">{copy.stepsCountLabel.replace("{count}", "4")}</span>
        </div>
        <ol className="steps-list">
          <li className="step-item"><span className="step-number">1</span><span><h3>{copy.bringInGameStep1Title}</h3><p>{copy.bringInGameStep1Text}</p></span></li>
          <li className="step-item"><span className="step-number">2</span><span><h3>{copy.bringInGameStep2Title}</h3><p>{copy.bringInGameStep2Text}</p></span></li>
          <li className="step-item"><span className="step-number">3</span><span><h3>{copy.bringInGameStep3Title}</h3><p>{copy.bringInGameStep3Text}</p></span></li>
          <li className="step-item"><span className="step-number">4</span><span><h3>{copy.bringInGameStep4Title}</h3><p>{copy.bringInGameStep4Text}</p></span></li>
        </ol>
      </section>
    </main>
  );
}
