import { useCopy } from "../../i18n/locale";
import type { GenerationTiming } from "./generationStore";

export type GenerationTimingBadgeProps = {
  timing: GenerationTiming | null | undefined;
  variant?: "neutral" | "gus";
};

/**
 * Convert persisted attempt timestamps into the compact display value.
 * Returns null for incomplete or unsafe server values so a badge can never
 * invent a duration from browser wall-clock time.
 */
export function formatGenerationDuration(
  timing: GenerationTiming | null | undefined,
): string | null {
  if (!timing) {
    return null;
  }
  const startedAt = Date.parse(timing.startedAt);
  const finishedAt = Date.parse(timing.finishedAt);
  if (!Number.isFinite(startedAt) || !Number.isFinite(finishedAt)) {
    return null;
  }
  const seconds = (finishedAt - startedAt) / 1000;
  if (!Number.isFinite(seconds) || seconds < 0) {
    return null;
  }
  return seconds < 10 ? seconds.toFixed(1) : String(Math.round(seconds));
}

export function GenerationTimingBadge({
  timing,
  variant = "neutral",
}: GenerationTimingBadgeProps) {
  const copy = useCopy();
  const duration = formatGenerationDuration(timing);
  if (duration === null) {
    return null;
  }

  const isGus = variant === "gus";
  const timingLabel = copy.generationTimingAriaLabel.replace(
    "{duration}",
    duration,
  );
  const accessibleLabel = isGus
    ? copy.generationTimingGusAriaLabel.replace("{duration}", duration)
    : timingLabel;
  const className = `generation-timing generation-timing--${variant}`;

  return (
    <div className={className} role="status" aria-label={accessibleLabel}>
      <div className="generation-timing__header">
        {isGus && (
          <span className="generation-timing__icon" aria-hidden="true">
            ✦
          </span>
        )}
        <span className="generation-timing__marker">
          {isGus
            ? copy.generationTimingGusMarker
            : copy.generationTimingNeutralMarker}
        </span>
      </div>
      {isGus && <p className="generation-timing__story">{copy.generationTimingGusStory}</p>}
      <p className="generation-timing__duration">
        {copy.generationTimingNeutral.replace("{duration}", duration)}
      </p>
    </div>
  );
}
