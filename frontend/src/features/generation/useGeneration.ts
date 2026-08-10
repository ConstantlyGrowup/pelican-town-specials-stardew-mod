import { useCallback, useEffect, useRef } from "react";
import { useSyncExternalStore } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { fetchGenerationProgress } from "../../api/ndjson";
import { useCopy } from "../../i18n/locale";
import {
  applyTerminalSnapshot,
  beginGeneration,
  cancelStream,
  getGenerationState,
  hasLiveStream,
  hydrateGeneration,
  subscribeGeneration,
} from "./generationStore";

export type {
  GenerationPhase,
  GenerationState,
} from "./generationStore";

export type { GenerationErrorEnvelope, GenerationStage } from "../../api/ndjson";

/** How often to poll the read-only progress endpoint while a generation runs
 * without an attached stream (refresh / page nav / reopened tab). */
const POLL_INTERVAL_MS = 2000;

type UseGenerationOptions = {
  draftId: string;
  onSuccess?: () => void;
  /** True while the owning page believes the draft is GENERATING/REGENERATING
   * (from the draft query). Enables server hydration + polling. */
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
 * - `begin` starts a fresh NDJSON stream; `cancel` awaits the backend `/cancel`
 *   (server rolls the draft back) before clearing local stream state.
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

  const state = useSyncExternalStore(
    subscribeGeneration,
    () => getGenerationState(draftId),
  );

  // Hydrate + poll while the server owns a generation but no live stream is
  // attached here. Stops at terminal state, on unmount, or when a stream is
  // started locally (the streaming path owns the state afterwards).
  useEffect(() => {
    if (!running || !draftId) {
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

    const tick = async () => {
      if (disposed) {
        return;
      }
      // A live stream owns the state; never poll while one is attached.
      if (hasLiveStream(draftId)) {
        stop();
        return;
      }
      let progress;
      try {
        progress = await fetchGenerationProgress(draftId);
      } catch {
        // Transient failure; the next poll tick retries.
        return;
      }
      if (disposed) {
        return;
      }
      if (progress.active && progress.attempt) {
        hydrateGeneration(draftId, progress);
      } else {
        stop();
        if (progress.attempt) {
          applyTerminalSnapshot(draftId, progress.attempt);
        } else {
          hydrateGeneration(draftId, progress);
        }
        if (progress.attempt?.status === "SUCCEEDED") {
          onSuccessRef.current?.();
        }
        void queryClient.invalidateQueries({ queryKey: ["draft", draftId] });
      }
    };

    void tick();
    timer = window.setInterval(() => void tick(), pollIntervalMs);
    return () => {
      disposed = true;
      stop();
    };
  }, [running, draftId, queryClient, pollIntervalMs]);

  const begin = useCallback(() => {
    beginGeneration(draftId, onSuccessRef.current, {
      streamError: copy.generationStreamError,
      cancelError: copy.cancelStreamError,
    });
  }, [draftId, copy.generationStreamError, copy.cancelStreamError]);

  const cancel = useCallback(async () => {
    await cancelStream(draftId, { cancelError: copy.cancelStreamError });
    void queryClient.invalidateQueries({ queryKey: ["draft", draftId] });
  }, [draftId, copy.cancelStreamError, queryClient]);

  return {
    phase: state.phase,
    currentStage: state.currentStage,
    succeededStages: state.succeededStages,
    totalStages: state.totalStages,
    error: state.error,
    begin,
    cancel,
  };
}
