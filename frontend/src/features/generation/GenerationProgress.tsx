import { PRODUCT_COPY } from "../../i18n/copy";
import type { GenerationStage } from "../../api/ndjson";

type GenerationProgressProps = {
  currentStage: GenerationStage | null;
  succeededStages: GenerationStage[];
  totalStages: number | null;
  preparingLabel?: string;
  onCancel?: () => void;
};

const GENERATION_STAGES: GenerationStage[] = [
  "INPUT_VALIDATION",
  "DISH_ANALYSIS",
  "GAMEPLAY_DESIGN",
  "INGREDIENT_MAPPING",
  "VISUAL_BRIEF",
  "ICON_GENERATION_AND_NORMALIZATION",
  "PREVIEW_ART_GENERATION_AND_COMPOSITION",
  "RESULT_VALIDATION",
  "ATOMIC_PROMOTION",
];

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
    <section className="card generation-card" aria-label={copy.generationProgressHeading}>
      <h2>{copy.generationProgressHeading}</h2>
      <div
        className="generation-live"
        aria-live="polite"
        aria-label={
          currentStage
            ? `当前阶段：${copy.generationStageLabels[currentStage]}`
            : undefined
        }
      >
        {preparingLabel && <p className="status-banner status-warning">{preparingLabel}</p>}
        {stageCountText && <p className="generation-count">{stageCountText}</p>}
      </div>
      <ol className="generation-stage-list">
        {GENERATION_STAGES.map((stage) => {
          const done = succeededStages.includes(stage);
          const current = currentStage === stage;
          return (
            <li
              key={stage}
              className={`generation-stage${done ? " done" : ""}${current ? " current" : ""}`}
              aria-current={current ? "step" : undefined}
            >
              <span className="generation-stage__marker" aria-hidden="true">
                {done ? "✓" : current ? "›" : "·"}
              </span>
              <span>{copy.generationStageLabels[stage]}</span>
            </li>
          );
        })}
      </ol>
      {onCancel && (
        <button className="btn btn-secondary" type="button" onClick={onCancel}>
          {copy.cancelGeneration}
        </button>
      )}
    </section>
  );
}
