import { useSyncExternalStore } from "react";
import { useQueryClient } from "@tanstack/react-query";
import {
  beginGeneration,
  cancelStream,
  getGenerationState,
  subscribeGeneration,
} from "./generationStore";

export type {
  GenerationPhase,
  GenerationState,
} from "./generationStore";

export type { GenerationErrorEnvelope, GenerationStage } from "../../api/ndjson";

type UseGenerationOptions = {
  draftId: string;
  onSuccess?: () => void;
};

/**
 * Thin wrapper over the module-level generation store.
 *
 * - `phase` transitions idle → streaming → success | error | cancelled.
 * - Stage state is derived only from real `stage.started` / `stage.succeeded`
 *   events; no synthetic percentages.
 * - State lives in `generationStore` keyed by draftId, so a stream keeps
 *   running across page navigation and is restored on remount.
 * - `cancel` awaits the backend `/cancel` (server rolls the draft back) before
 *   clearing local stream state and invalidating the draft query.
 */
export function useGeneration({ draftId, onSuccess }: UseGenerationOptions) {
  const queryClient = useQueryClient();

  const state = useSyncExternalStore(
    subscribeGeneration,
    () => getGenerationState(draftId),
  );

  const begin = () => {
    beginGeneration(draftId, onSuccess);
  };

  const cancel = async () => {
    await cancelStream(draftId);
    void queryClient.invalidateQueries({ queryKey: ["draft", draftId] });
  };

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
