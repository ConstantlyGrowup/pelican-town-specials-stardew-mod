import { useCallback, useEffect, useRef } from "react";
import { useSyncExternalStore } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { fetchGenerationProgress } from "../../api/ndjson";
import { useCopy } from "../../i18n/locale";
import {
  applyTerminalSnapshot,
  beginGeneration,
  cancelStream,
  clearGenerationTiming,
  getGenerationState,
  hasLiveStream,
  hydrateGeneration,
  subscribeGeneration,
} from "./generationStore";

export type {
  GenerationPhase,
  GenerationState,
  TrialUsageFact,
} from "./generationStore";

export type { GenerationErrorEnvelope, GenerationStage } from "../../api/ndjson";

/** How often to poll the read-only progress endpoint while a generation runs
 * without an attached stream (refresh / page nav / reopened tab). */
const POLL_INTERVAL_MS = 2000;

type UseGenerationOptions = {
  draftId: string;
  onSuccess?: () => void | Promise<void>;
  /** True while the owning page believes the draft is GENERATING/REGENERATING
   * (from the draft query). Keeps retry polling active after a transient read
   * failure; the initial read happens for every mounted draft. */
  running?: boolean;
  /** Poll interval override (tests use a tiny value; production keeps 2s). */
  pollIntervalMs?: number;
};

/**
 * Thin wrapper over the module-level generation store, with Task 19.5 server
 * hydration and polling.
 *
 * - `phase` transitions idle → streaming → success | error | cancelled.
 * - When the page mounts with a draft the server is still generating
 *   (``running``) and no live stream is attached (refresh / page nav / reopened
 *   tab), the persisted attempt hydrates the store and the progress endpoint is
 *   polled until the attempt terminates. The module store is a cache; the
 *   server snapshot wins on conflict.
 * - `begin` starts the default NDJSON stream (the backend resumes a compatible
 *   checkpoint or starts a new attempt); `restart` starts explicitly from
 *   scratch. `cancel` awaits the backend `/cancel` (server rolls the draft
 *   back) before clearing local stream state.
 */
export function useGeneration({
  draftId,
  onSuccess,
  running = false,
  pollIntervalMs = POLL_INTERVAL_MS,
}: UseGenerationOptions) {
  const queryClient = useQueryClient();
  const copy = useCopy();
  const onSuccessRef = useRef(onSuccess);
  onSuccessRef.current = onSuccess;
  const notifiedAttemptRef = useRef<string | null>(null);
  const progressReadSequenceRef = useRef(0);

  const state = useSyncExternalStore(
    subscribeGeneration,
    () => getGenerationState(draftId),
  );

  const readLatestProgress = useCallback(async () => {
    const requestSequence = progressReadSequenceRef.current + 1;
    progressReadSequenceRef.current = requestSequence;
    const progress = await fetchGenerationProgress(draftId);
    if (requestSequence !== progressReadSequenceRef.current) {
      return null;
    }
    return { progress, requestSequence };
  }, [draftId]);

  const refreshTerminalProgress = useCallback(async (expectedAttemptId: string) => {
    if (!draftId) {
      return;
    }
    try {
      const latestRead = await readLatestProgress();
      if (!latestRead) {
        return;
      }
      const { progress, requestSequence } = latestRead;
      if (
        progress.active ||
        progress.attempt?.status !== "SUCCEEDED" ||
        progress.attempt.attemptId !== expectedAttemptId ||
        requestSequence !== progressReadSequenceRef.current ||
        getGenerationState(draftId).attemptId !== expectedAttemptId
      ) {
        return;
      }
      applyTerminalSnapshot(draftId, progress.attempt);
    } catch {
      // The terminal progress refresh is best-effort; the page remains on the
      // successful stream state and a later mount can restore persisted time.
    }
  }, [draftId, readLatestProgress]);

  const onLocalSuccess = useCallback(
    async (attemptId?: string) => {
      if (!attemptId) {
        return;
      }
      try {
        // Wait for the owning page to refetch its DraftView before the
        // terminal timing can be paired with its provenance.
        await onSuccessRef.current?.();
      } catch {
        // A failed query refresh must not expose timing beside stale result
        // provenance. A later mount can restore the persisted attempt.
        return;
      }
      if (getGenerationState(draftId).attemptId !== attemptId) {
        return;
      }
      notifiedAttemptRef.current = attemptId;
      // NDJSON success has no timestamps. Read the persisted terminal attempt
      // instead of measuring when the stream line arrived in the browser.
      void refreshTerminalProgress(attemptId);
    },
    [draftId, refreshTerminalProgress],
  );

  // Read one persisted snapshot on every draft-page mount, including
  // REVIEWABLE results. If the server reports active work, continue polling
  // until its terminal attempt is available. These reads never call begin().
  useEffect(() => {
    if (!draftId) {
      return;
    }
    let disposed = false;
    let timer: number | null = null;

    const stop = () => {
      if (timer !== null) {
        window.clearInterval(timer);
        timer = null;
      }
    };

    const schedule = () => {
      if (timer === null) {
        timer = window.setInterval(() => void tick(), pollIntervalMs);
      }
    };

    const tick = async () => {
      if (disposed) {
        return;
      }
      // A live stream owns the state; never poll while one is attached.
      if (hasLiveStream(draftId)) {
        stop();
        return;
      }
      let latestRead;
      try {
        latestRead = await readLatestProgress();
      } catch {
        // Transient failure; the next poll tick retries.
        if (running) {
          schedule();
        }
        return;
      }
      if (!latestRead) {
        return;
      }
      const { progress, requestSequence } = latestRead;
      if (
        disposed ||
        requestSequence !== progressReadSequenceRef.current ||
        hasLiveStream(draftId)
      ) {
        return;
      }
      if (progress.active && progress.attempt) {
        hydrateGeneration(draftId, progress);
        schedule();
      } else {
        stop();
        if (progress.attempt) {
          if (
            progress.attempt.status === "SUCCEEDED" &&
            progress.attempt.attemptId !== notifiedAttemptRef.current
          ) {
            clearGenerationTiming(draftId);
            try {
              // A cached DraftView may still describe the result replaced by
              // this attempt, including on a REVIEWABLE mount. Refresh it
              // before exposing the new timing beside its provenance.
              await onSuccessRef.current?.();
            } catch {
              return;
            }
            if (
              disposed ||
              requestSequence !== progressReadSequenceRef.current ||
              hasLiveStream(draftId)
            ) {
              return;
            }
            notifiedAttemptRef.current = progress.attempt.attemptId;
          }
          applyTerminalSnapshot(draftId, progress.attempt);
          if (running) {
            void queryClient.invalidateQueries({ queryKey: ["draft", draftId] });
          }
        } else {
          hydrateGeneration(draftId, progress);
        }
      }
    };

    void tick();
    if (running) {
      schedule();
    }
    return () => {
      disposed = true;
      stop();
      progressReadSequenceRef.current += 1;
    };
  }, [running, draftId, queryClient, pollIntervalMs, readLatestProgress]);

  const start = useCallback(
    (restart: boolean, regenerationInstructions?: string) => {
      progressReadSequenceRef.current += 1;
      notifiedAttemptRef.current = null;
      beginGeneration(draftId, onLocalSuccess, {
        streamError: copy.generationStreamError,
        cancelError: copy.cancelStreamError,
      }, {
        restart,
        regenerationInstructions,
      });
    },
    [draftId, onLocalSuccess, copy.generationStreamError, copy.cancelStreamError],
  );

  const begin = useCallback(
    (regenerationInstructions?: unknown) => {
      // The callback is also passed directly to legacy button onClick props;
      // React supplies a MouseEvent in that case. Only a string is a valid
      // Task59 instruction.
      start(
        false,
        typeof regenerationInstructions === "string"
          ? regenerationInstructions
          : undefined,
      );
    },
    [start],
  );

  const restart = useCallback(
    (regenerationInstructions?: unknown) => {
      start(
        true,
        typeof regenerationInstructions === "string"
          ? regenerationInstructions
          : undefined,
      );
    },
    [start],
  );

  const cancel = useCallback(async () => {
    progressReadSequenceRef.current += 1;
    await cancelStream(draftId, { cancelError: copy.cancelStreamError });
    void queryClient.invalidateQueries({ queryKey: ["draft", draftId] });
  }, [draftId, copy.cancelStreamError, queryClient]);

  return {
    phase: state.phase,
    attemptId: state.attemptId,
    currentStage: state.currentStage,
    succeededStages: state.succeededStages,
    totalStages: state.totalStages,
    timing: state.timing,
    trialUsage: state.trialUsage,
    regenerationInstructions: state.regenerationInstructions,
    error: state.error,
    begin,
    restart,
    cancel,
  };
}
