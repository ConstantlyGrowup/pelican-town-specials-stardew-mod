import { useCopy } from "../../i18n/locale";
import type { TrialUsageFact } from "./generationStore";

export type TrialUsageBadgeProps = {
  fact: TrialUsageFact | null | undefined;
};

function isValidRemaining(value: number): boolean {
  return Number.isFinite(value) && Number.isInteger(value) && value >= 0;
}

/**
 * A compact, non-interactive result fact. The store already validates the
 * persisted attempt, but the component keeps the same fail-closed boundary
 * when rendered directly or by a future caller.
 */
export function TrialUsageBadge({ fact }: TrialUsageBadgeProps) {
  const copy = useCopy();
  if (!fact || !isValidRemaining(fact.remaining)) {
    return null;
  }

  const remaining = String(fact.remaining);
  const visibleLabel = copy.trialUsageBadge.replace("{remaining}", remaining);
  const accessibleLabel = copy.trialUsageAriaLabel.replace(
    "{remaining}",
    remaining,
  );

  return (
    <div className="trial-usage-badge" role="status" aria-label={accessibleLabel}>
      <span className="trial-usage-badge__marker" aria-hidden="true">
        ✦
      </span>
      <span className="trial-usage-badge__label">{visibleLabel}</span>
    </div>
  );
}
