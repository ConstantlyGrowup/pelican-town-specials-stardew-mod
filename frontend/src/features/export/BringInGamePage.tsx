import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { apiClient } from "../../api/client";
import type { components } from "../../api/generated/schema";
import { PRODUCT_COPY } from "../../i18n/copy";

type ExportRecordView = components["schemas"]["ExportRecordView"];

export function BringInGamePage() {
  const copy = PRODUCT_COPY.zh;
  const { exportId } = useParams<{ exportId: string }>();
  const [folderError, setFolderError] = useState<string | null>(null);

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
      setFolderError(copy.openFolderFailed);
    }
  }

  function onDownload() {
    window.location.href = `/api/v1/exports/${exportId ?? ""}/download`;
  }

  if (query.isLoading) {
    return (
      <main>
        <h1>{copy.bringInGameTitle}</h1>
        <p>{copy.loading}</p>
      </main>
    );
  }

  if (query.isError || !query.data) {
    return (
      <main>
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
    <main>
      <h1>{copy.bringInGameTitle}</h1>
      <p>{copy.bringInGameSubtitle}</p>

      <section className="card">
        <h2>{record.spec.packDisplayName}</h2>
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
        {folderError && <div className="status-banner status-error">{folderError}</div>}
      </section>

      <section className="card">
        <h2>{copy.bringInGameStep1Title}</h2>
        <p>{copy.bringInGameStep1Text}</p>
        <h2>{copy.bringInGameStep2Title}</h2>
        <p>{copy.bringInGameStep2Text}</p>
        <h2>{copy.bringInGameStep3Title}</h2>
        <p>{copy.bringInGameStep3Text}</p>
        <h2>{copy.bringInGameStep4Title}</h2>
        <p>{copy.bringInGameStep4Text}</p>
      </section>
    </main>
  );
}
