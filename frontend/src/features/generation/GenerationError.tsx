import { PRODUCT_COPY } from "../../i18n/copy";
import type { GenerationErrorEnvelope } from "../../api/ndjson";

type GenerationErrorProps = {
  error: GenerationErrorEnvelope;
  onRetry?: () => void;
};

/**
 * Renders a generation ErrorEnvelope with an optional retry entry. The old
 * draft result remains visible on the page while this is shown, so a failed
 * regeneration degrades gracefully.
 */
export function GenerationError({ error, onRetry }: GenerationErrorProps) {
  const copy = PRODUCT_COPY.zh;
  return (
    <div className="status-banner status-error">
      <p>{error.message}</p>
      {onRetry && (
        <button className="btn" type="button" onClick={onRetry}>
          {copy.retryGeneration}
        </button>
      )}
    </div>
  );
}
