import { useCopy } from "../../i18n/locale";
import type { GenerationErrorEnvelope } from "../../api/ndjson";

type GenerationErrorProps = {
  error: GenerationErrorEnvelope;
  onRetry?: () => void;
};

/** Backend code rejecting a generate request when all 3 slots are busy
 * (M8 Task 28/29). The backend message stays frozen; the UI replaces it with
 * the localized limit hint below. `error.details` is never parsed. */
const GENERATION_BUSY_CODE = "PTS_GEN_BUSY";

/** Backend code rejecting a generate request when the trial quota is used up
 * (Task 30). The backend message stays frozen; the UI replaces it with the
 * localized trial-limit hint so the newcomer sees the same phrasing as on the
 * Settings trial panel. */
const TRIAL_LIMIT_CODE = "PTS_TRIAL_LIMIT_REACHED";

/**
 * Renders a generation ErrorEnvelope with an optional retry entry. The old
 * draft result remains visible on the page while this is shown, so a failed
 * regeneration degrades gracefully. A busy rejection (4th concurrent
 * generation) shows the bilingual capacity-limit hint instead of the raw
 * backend message, and an exhausted trial quota (Task 30) shows the
 * bilingual trial-limit hint; every other error keeps the backend message.
 */
export function GenerationError({ error, onRetry }: GenerationErrorProps) {
  const copy = useCopy();
  const message =
    error.code === GENERATION_BUSY_CODE
      ? copy.generationBusyLimit
      : error.code === TRIAL_LIMIT_CODE
        ? copy.trialLimitReached
        : error.message;
  return (
    <div className="status-banner status-error" role="alert">
      <p>{message}</p>
      {onRetry && (
        <button className="btn" type="button" onClick={onRetry}>
          {copy.retryGeneration}
        </button>
      )}
    </div>
  );
}
