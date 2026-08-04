import { PRODUCT_COPY } from "../../i18n/copy";
import type { GenerationStage } from "../../api/ndjson";

type GenerationProgressProps = {
  currentStage: GenerationStage | null;
  succeededStages: GenerationStage[];
  totalStages: number | null;
  preparingLabel?: string;
  onCancel?: () => void;
};

/**
 * Progress UI driven purely by real stage events. The completed count is the
 * number of `stage.succeeded` events received; there is no synthetic
 * percentage.
 */
export function GenerationProgress({
  currentStage,
  succeededStages,
  totalStages,
  preparingLabel,
  onCancel,
}: GenerationProgressProps) {
  const copy = PRODUCT_COPY.zh;
  const completed = succeededStages.length;
  const total = totalStages;
  const stageCountText =
    total === null
      ? null
      : copy.stagesCompleted
          .replace("{succeeded}", String(completed))
          .replace("{total}", String(total));

  return (
    <section className="card" aria-label={copy.generationProgressHeading}>
      <h2>{copy.generationProgressHeading}</h2>
      {preparingLabel && <p className="status-banner status-warning">{preparingLabel}</p>}
      {currentStage && <p>{copy.generationStageLabels[currentStage]}</p>}
      {stageCountText && <p>{stageCountText}</p>}
      {onCancel && (
        <button className="btn" type="button" onClick={onCancel}>
          {copy.cancelGeneration}
        </button>
      )}
    </section>
  );
}
