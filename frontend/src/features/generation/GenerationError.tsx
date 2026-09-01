import { useCopy, useLocale } from "../../i18n/locale";
import type { Copy } from "../../i18n/copy";
import type { GenerationErrorEnvelope } from "../../api/ndjson";

type GenerationErrorProps = {
  error: GenerationErrorEnvelope;
  onRetry?: () => void | Promise<void>;
  onTakeover?: () => void | Promise<void>;
  onConfigure?: () => void | Promise<void>;
  onDiscard?: () => void | Promise<void>;
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

/** Only copy entries that are plain strings can stand in for a message. */
type CopyMessageKey = {
  [K in keyof Copy]: Copy[K] extends string ? K : never;
}[keyof Copy];

/**
 * Backend generation error codes whose messages are fixed strings. They map
 * to localized copy in every locale; the zh strings intentionally mirror the
 * backend messages one-to-one, so mapping them changes nothing for zh-CN
 * while keeping the banner re-localizable when the language is switched.
 */
const GENERATION_ERROR_KEYS: Record<string, CopyMessageKey> = {
  [GENERATION_BUSY_CODE]: "generationBusyLimit",
  [TRIAL_LIMIT_CODE]: "trialLimitReached",
  [TRIAL_SERVICE_UNAVAILABLE_CODE]: "trialServiceUnavailable",
  PTS_DRAFT_NOT_FOUND: "errDraftNotFound",
  PTS_STATE_ILLEGAL_TRANSITION: "errDraftStateBlocked",
  PTS_IMAGE_INPUT_UNSUPPORTED: "errImageInputUnsupported",
  PTS_PREVIEW_PROMPT_TOO_LONG: "errPreviewPromptTooLong",
  PTS_GEN_LOW_CONFIDENCE: "errLowConfidence",
  PTS_GEN_VALIDATION_FAILED: "errGenerationValidationFailed",
  PTS_PROVIDER_IMAGE_EDIT_UNSUPPORTED: "errImageEditUnsupported",
  PTS_STATE_REVISION_CONFLICT: "errGenerationStale",
  PTS_GEN_CANCELLED: "errGenerationCancelled",
  PTS_GEN_INTERRUPTED: "errGenerationInterrupted",
  PTS_GEN_UNEXPECTED: "errGenerationUnexpected",
  PTS_PROVIDER_NOT_CONFIGURED: "errProviderNotConfigured",
  PTS_PROVIDER_REQUEST_FAILED: "errProviderRequestFailed",
  PTS_PROVIDER_IMAGE_INVALID: "errProviderImageInvalid",
  PTS_PROVIDER_INVALID_STRUCTURED_OUTPUT: "errProviderStructuredOutputInvalid",
  PTS_PROVIDER_RATE_LIMITED: "errProviderRateLimited",
};

/**
 * Provider codes whose backend messages vary by failure mode (missing vs
 * invalid key, timeout vs outage). The backend wording stays authoritative
 * for zh-CN, while en-US shows one merged, actionable phrase instead of the
 * Chinese backend message.
 */
const PROVIDER_FALLBACK_KEYS_EN: Record<string, CopyMessageKey> = {
  PTS_PROVIDER_AUTH_FAILED: "errProviderAuthFailed",
  PTS_PROVIDER_UNAVAILABLE: "errProviderUnavailable",
};

/**
 * Renders a generation ErrorEnvelope with an optional retry entry. The old
 * draft result remains visible on the page while this is shown, so a failed
 * regeneration degrades gracefully. Known backend codes render localized copy
 * instead of the raw (Chinese) backend message, so the English UI never shows
 * Chinese error text; unknown codes keep the backend message as the
 * diagnostic fallback.
 */
export function GenerationError({
  error,
  onRetry,
  onTakeover,
  onConfigure,
  onDiscard,
  actionPending = false,
}: GenerationErrorProps) {
  const copy = useCopy();
  const locale = useLocale();
  const trialServiceUnavailable = error.code === TRIAL_SERVICE_UNAVAILABLE_CODE;
  const trialLimitReached = error.code === TRIAL_LIMIT_CODE;
  const personalProviderConfigured =
    error.details?.personalProviderConfigured === true;
  const copyKey =
    GENERATION_ERROR_KEYS[error.code] ??
    (locale === "en-US" ? PROVIDER_FALLBACK_KEYS_EN[error.code] : undefined);
  const message = copyKey ? copy[copyKey] : error.message;
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
      {trialServiceUnavailable && onDiscard && (
        <button
          className="btn"
          type="button"
          onClick={() => void onDiscard()}
          disabled={actionPending}
        >
          {copy.discardDraftAndReturnHome}
        </button>
      )}
      {onRetry && (
        <button
          className="btn"
          type="button"
          onClick={() => void onRetry()}
          disabled={actionPending}
        >
          {trialServiceUnavailable ? copy.retryNow : copy.retryGeneration}
        </button>
      )}
    </div>
  );
}
