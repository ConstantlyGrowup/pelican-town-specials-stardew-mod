import {
  cancelGeneration,
  streamGeneration,
  GenerationCancelError,
  GenerationRequestError,
  type GenerationAttemptPublic,
  type GenerationErrorEnvelope,
  type GenerationEvent,
  type GenerationProgress,
  type GenerationStage,
} from "../../api/ndjson";

export type GenerationPhase =
  | "idle"
  | "streaming"
  | "success"
  | "error"
  | "cancelled";

export type GenerationTiming = {
  startedAt: string;
  finishedAt: string;
};

export type GenerationState = {
  phase: GenerationPhase;
  /** Persisted attempt identity used to reject stale progress snapshots. */
  attemptId: string | null;
  currentStage: GenerationStage | null;
  succeededStages: GenerationStage[];
  totalStages: number | null;
  error: GenerationErrorEnvelope | null;
  /** Timing from the latest terminal SUCCEEDED attempt, never browser time. */
  timing: GenerationTiming | null;
};

type InternalState = GenerationState & {
  controller: AbortController | null;
  /** Referentially stable snapshot for useSyncExternalStore. */
  _snapshot: GenerationState;
};

type Listener = () => void;

/**
 * Module-level generation state keyed by draftId. Generation streams continue
 * while the user navigates away from the draft page and are restored on
 * remount. Follows the `selectionStore.ts` module-store + listener pattern.
 */
const states = new Map<string, InternalState>();
const listeners = new Set<Listener>();

/**
 * In-flight cancel operations keyed by draftId (single-flight). While a cancel
 * is pending for a draft, repeated cancels return the same operation instead of
 * issuing a second request or running a second terminal-state write.
 */
const pendingCancels = new Map<string, Promise<void>>();

function emit() {
  for (const listener of listeners) {
    listener();
  }
}

function getState(draftId: string): InternalState {
  let state = states.get(draftId);
  if (!state) {
    const idle: GenerationState = {
      phase: "idle",
      attemptId: null,
      currentStage: null,
      succeededStages: [],
      totalStages: null,
      error: null,
      timing: null,
    };
    state = { ...idle, controller: null, _snapshot: idle };
    states.set(draftId, state);
  }
  return state;
}

function setState(draftId: string, patch: Partial<GenerationState>) {
  const state = getState(draftId);
  const next: GenerationState = {
    phase: patch.phase ?? state.phase,
    attemptId:
      patch.attemptId !== undefined ? patch.attemptId : state.attemptId,
    currentStage:
      patch.currentStage !== undefined ? patch.currentStage : state.currentStage,
    succeededStages: patch.succeededStages ?? state.succeededStages,
    totalStages:
      patch.totalStages !== undefined ? patch.totalStages : state.totalStages,
    error: patch.error !== undefined ? patch.error : state.error,
    timing: patch.timing !== undefined ? patch.timing : state.timing,
  };
  states.set(draftId, { ...next, controller: state.controller, _snapshot: next });
  emit();
}

export function getGenerationState(draftId: string): GenerationState {
  return getState(draftId)._snapshot;
}

/** Hide any previous successful duration while a newer result is reconciled. */
export function clearGenerationTiming(draftId: string): void {
  if (getState(draftId).timing !== null) {
    setState(draftId, { timing: null });
  }
}

/** True while a live NDJSON stream is attached for this draft. */
export function hasLiveStream(draftId: string): boolean {
  const state = getState(draftId);
  return state.controller !== null && state.phase === "streaming";
}

function timingFromAttempt(attempt: GenerationAttemptPublic): GenerationTiming | null {
  if (attempt.status !== "SUCCEEDED" || !attempt.finishedAt) {
    return null;
  }
  return {
    startedAt: attempt.startedAt,
    finishedAt: attempt.finishedAt,
  };
}

/**
 * Hydrate a draft's generation state from a read-only server snapshot.
 *
 * Task 19.5: on refresh / page nav / reopened tab there is no live NDJSON
 * stream, so the persisted attempt (single source of truth) restores the
 * progress UI. A live stream that is still running for this draft is never
 * overwritten — the streaming path owns the state until it terminates.
 */
export function hydrateGeneration(
  draftId: string,
  progress: GenerationProgress,
): void {
  const current = getState(draftId);
  if (current.controller !== null && current.phase === "streaming") {
    // A live stream is attached and authoritative; do not clobber it.
    return;
  }
  const attempt = progress.attempt;
  if (progress.active && attempt) {
    if (
      (current.phase === "success" ||
        current.phase === "error" ||
        current.phase === "cancelled") &&
      current.attemptId === attempt.attemptId
    ) {
      // A stale active poll must not roll a terminal snapshot for the same
      // attempt back to streaming.
      return;
    }
    const succeededStages = attempt.stages
      .filter((stage) => stage.status === "SUCCEEDED")
      .map((stage) => stage.stage);
    // `attempt.stages` only records stages reached so far, so the total comes
    // from the explicit `totalStages` field the orchestrator persists per run.
    const totalStages = attempt.totalStages ?? null;
    const streaming: GenerationState = {
      phase: "streaming",
      attemptId: attempt.attemptId,
      currentStage: attempt.currentStage ?? null,
      succeededStages,
      totalStages,
      error: null,
      // A new active attempt must never inherit the last successful duration.
      timing: null,
    };
    states.set(draftId, { ...streaming, controller: null, _snapshot: streaming });
    emit();
    return;
  }

  if (attempt) {
    applyTerminalSnapshot(draftId, attempt);
    return;
  }

  // A terminal local stream is still authoritative when a transient progress
  // response has no attempt. A real terminal attempt is handled above and can
  // clear timing for failed/cancelled generations.
  if (current.controller !== null && current.phase !== "idle") {
    return;
  }
  if (
    current.phase !== "idle" ||
    current.attemptId !== null ||
    current.timing !== null
  ) {
    setState(draftId, {
      phase: "idle",
      attemptId: null,
      currentStage: null,
      succeededStages: [],
      totalStages: null,
      error: null,
      timing: null,
    });
  }
}

/**
 * Reflect a terminal server snapshot in the store (the persisted attempt is the
 * single source of truth). Called by the progress poll when a generation ends
 * server-side while no live stream is attached (e.g. after a refresh).
 */
export function applyTerminalSnapshot(
  draftId: string,
  attempt: GenerationAttemptPublic,
): void {
  const current = getState(draftId);
  if (current.controller !== null && current.phase === "streaming") {
    return;
  }
  let phase: GenerationPhase;
  let error: GenerationErrorEnvelope | null = null;
  switch (attempt.status) {
    case "SUCCEEDED":
      phase = "success";
      break;
    case "FAILED":
      phase = "error";
      error = attempt.error
        ? {
            code: attempt.error.code,
            message: attempt.error.message,
            retryable: attempt.error.retryable,
            requestId: attempt.error.requestId,
            recommendedAction: "",
          }
        : null;
      break;
    default:
      // CANCELLED / INTERRUPTED
      phase = "cancelled";
      break;
  }
  const terminal: GenerationState = {
    phase,
    attemptId: attempt.attemptId,
    currentStage: null,
    succeededStages: current.succeededStages,
    totalStages: current.totalStages,
    error,
    timing: timingFromAttempt(attempt),
  };
  states.set(draftId, { ...terminal, controller: null, _snapshot: terminal });
  emit();
}

export function subscribeGeneration(listener: Listener): () => void {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

/** Locale-aware fallback messages for the module store (M7 Task 25). */
export type GenerationFallbackMessages = {
  /** Shown when an unexpected stream error has no structured envelope. */
  streamError: string;
  /** Shown when a cancel request fails without a structured envelope. */
  cancelError: string;
};

type GenerationSuccessHandler = (attemptId?: string) => void | Promise<void>;

export function beginGeneration(
  draftId: string,
  onSuccess?: GenerationSuccessHandler,
  fallback?: GenerationFallbackMessages,
): void {
  const state = getState(draftId);
  state.controller?.abort();
  const controller = new AbortController();
  const streaming: GenerationState = {
    phase: "streaming",
    attemptId: null,
    currentStage: null,
    succeededStages: [],
    totalStages: null,
    error: null,
    timing: null,
  };
  states.set(draftId, {
    ...streaming,
    controller,
    _snapshot: streaming,
  });
  emit();

  void (async () => {
    try {
      await streamGeneration({ draftId, signal: controller.signal }, (event) => {
        handleEvent(draftId, controller, event, onSuccess);
      });
    } catch (cause) {
      const current = getState(draftId);
      if (current.controller !== controller) {
        return;
      }
      if (controller.signal.aborted) {
        // A user cancel may already have reported a failure envelope; do not
        // overwrite it with a generic cancelled state.
        if (current.phase !== "error") {
          setState(draftId, { phase: "cancelled", timing: null });
        }
        return;
      }
      if (cause instanceof GenerationRequestError) {
        setState(draftId, {
          phase: "error",
          error: cause.envelope,
          timing: null,
        });
        return;
      }
      setState(draftId, {
        phase: "error",
        timing: null,
        error: {
          code: "PTS_GEN_STREAM_ERROR",
          message: cause instanceof Error
            ? cause.message
            : fallback?.streamError ?? "Generation stream error",
          retryable: true,
          requestId: "",
          recommendedAction: "",
        },
      });
    }
  })();
}

function handleEvent(
  draftId: string,
  controller: AbortController,
  event: GenerationEvent,
  onSuccess: GenerationSuccessHandler | undefined,
) {
  const current = getState(draftId);
  if (current.controller !== controller) {
    return;
  }
  switch (event.type) {
    case "attempt.started":
      setState(draftId, { attemptId: event.attemptId, timing: null });
      break;
    case "stage.started":
      setState(draftId, {
        attemptId: event.attemptId,
        currentStage: event.stage,
        totalStages: event.total,
      });
      break;
    case "stage.succeeded":
      setState(draftId, {
        attemptId: event.attemptId,
        succeededStages: current.succeededStages.includes(event.stage)
          ? current.succeededStages
          : [...current.succeededStages, event.stage],
        currentStage:
          current.currentStage === event.stage ? null : current.currentStage,
      });
      break;
    case "attempt.succeeded":
      setState(draftId, {
        phase: "success",
        attemptId: event.attemptId,
        // The NDJSON event has no persisted timestamps. The caller refreshes
        // GET generation progress to obtain the authoritative timing.
        timing: null,
      });
      void onSuccess?.(event.attemptId);
      break;
    case "attempt.failed":
      setState(draftId, {
        phase: "error",
        attemptId: event.attemptId,
        error: event.error,
        timing: null,
      });
      break;
  }
}

/**
 * Cancel a generation. The backend /cancel is awaited FIRST so the server rolls
 * the draft back; only then is the local stream aborted and terminal state set.
 *
 * Cancels are single-flight per draft: while one is pending, repeated cancels
 * reuse the same operation (no second request, no second terminal-state write).
 * The controller is captured when the cancel starts; a newer begin() installs a
 * fresh controller, and a stale cancel never aborts or marks that new round.
 */
export async function cancelStream(
  draftId: string,
  fallback?: Pick<GenerationFallbackMessages, "cancelError">,
): Promise<void> {
  const inFlight = pendingCancels.get(draftId);
  if (inFlight) {
    return inFlight;
  }
  const captured = getState(draftId).controller;
  const operation = (async () => {
    let envelope: GenerationErrorEnvelope | null = null;
    try {
      await cancelGeneration(draftId);
    } catch (cause) {
      envelope =
        cause instanceof GenerationCancelError
          ? cause.envelope
          : {
              code: "PTS_GEN_CANCEL_FAILED",
              message: cause instanceof Error
                ? cause.message
                : fallback?.cancelError ?? "Cancel failed",
              retryable: true,
              requestId: "",
              recommendedAction: "",
            };
    } finally {
      const current = getState(draftId);
      if (current.controller === captured) {
        captured?.abort();
        if (envelope) {
          setState(draftId, { phase: "error", error: envelope, timing: null });
        } else {
          setState(draftId, { phase: "cancelled", error: null, timing: null });
        }
      }
    }
  })();
  pendingCancels.set(draftId, operation);
  try {
    return await operation;
  } finally {
    pendingCancels.delete(draftId);
  }
}

/** Test helper: aborts all streams and clears module-level state. */
export function resetGenerationStore() {
  for (const state of states.values()) {
    state.controller?.abort();
  }
  states.clear();
  pendingCancels.clear();
  emit();
}
