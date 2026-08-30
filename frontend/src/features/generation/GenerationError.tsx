import { useCopy } from "../../i18n/locale";
import type { GenerationErrorEnvelope } from "../../api/ndjson";

type GenerationErrorProps = {
  error: GenerationErrorEnvelope;
  onRetry?: () => void | Promise<void>;
  onTakeover?: () => void | Promise<void>;
  onConfigure?: () => void | Promise<void>;
  actionPending?: boolean;
};

/** Backend code rejecting a generate request when all 3 slots are busy
 * (M8 Task 28/29). The backend message stays frozen; the UI replaces it with
 * the localized limit hint below. */
const GENERATION_BUSY_CODE = "PTS_GEN_BUSY";

/** Backend code rejecting a generate request when the trial quota is used up
 * (Task 30). The backend message stays frozen; the UI replaces it with the
 * localized trial-limit hint so the newcomer sees the same phrasing as on the
 * Settings trial panel. */
const TRIAL_LIMIT_CODE = "PTS_TRIAL_LIMIT_REACHED";

/** Backend code for a transient trial-provider failure. The UI replaces the
 * backend message so provider configuration details can never become user
 * copy, while preserving the retry-safe explanation. */
const TRIAL_SERVICE_UNAVAILABLE_CODE = "PTS_TRIAL_SERVICE_UNAVAILABLE";

/**
 * Renders a generation ErrorEnvelope with an optional retry entry. The old
 * draft result remains visible on the page while this is shown, so a failed
 * regeneration degrades gracefully. A busy rejection (4th concurrent
 * generation) shows the bilingual capacity-limit hint instead of the raw
 * backend message, and an exhausted trial quota (Task 30) shows the
 * bilingual trial-limit hint; every other error keeps the backend message.
 */
export function GenerationError({
  error,
  onRetry,
  onTakeover,
  onConfigure,
  actionPending = false,
}: GenerationErrorProps) {
  const copy = useCopy();
  const trialServiceUnavailable = error.code === TRIAL_SERVICE_UNAVAILABLE_CODE;
  const trialLimitReached = error.code === TRIAL_LIMIT_CODE;
  const personalProviderConfigured =
    error.details?.personalProviderConfigured === true;
  const message =
    error.code === GENERATION_BUSY_CODE
      ? copy.generationBusyLimit
      : error.code === TRIAL_LIMIT_CODE
        ? copy.trialLimitReached
        : error.code === TRIAL_SERVICE_UNAVAILABLE_CODE
          ? copy.trialServiceUnavailable
        : error.message;
  return (
    <div className="status-banner status-error" role="alert">
      <p>{message}</p>
      {trialServiceUnavailable && personalProviderConfigured && onTakeover && (
        <button
          className="btn"
          type="button"
          onClick={() => void onTakeover()}
          disabled={actionPending}
        >
          {copy.usePersonalProvider}
        </button>
      )}
      {((trialServiceUnavailable && !personalProviderConfigured) ||
        trialLimitReached) &&
        onConfigure && (
          <button
            className="btn"
            type="button"
            onClick={() => void onConfigure()}
            disabled={actionPending}
          >
            {copy.configurePersonalProvider}
          </button>
        )}
      {onRetry && (
        <button
          className="btn"
          type="button"
          onClick={() => void onRetry()}
          disabled={actionPending}
        >
          {trialServiceUnavailable ? copy.retryLater : copy.retryGeneration}
        </button>
      )}
    </div>
  );
}
