import { useCallback, useEffect, useRef, useState } from "react";
import {
  cancelGeneration,
  streamGeneration,
  type GenerationErrorEnvelope,
  type GenerationEvent,
  type GenerationStage,
} from "../../api/ndjson";

export type GenerationPhase = "idle" | "streaming" | "success" | "error" | "cancelled";

type UseGenerationOptions = {
  draftId: string;
  onSuccess?: () => void;
};

/**
 * Drives a generation NDJSON stream for a single draft.
 *
 * - `phase` transitions idle → streaming → success | error | cancelled.
 * - Stage state is derived only from real `stage.started` / `stage.succeeded`
 *   events; no synthetic percentages.
 * - `begin` restarts cleanly from any phase, so cancelled/failed runs leave the
 *   page fully recoverable.
 * - `cancel` aborts the stream and best-effort POSTs the cancel endpoint.
 */
export function useGeneration({ draftId, onSuccess }: UseGenerationOptions) {
  const [phase, setPhase] = useState<GenerationPhase>("idle");
  const [currentStage, setCurrentStage] = useState<GenerationStage | null>(null);
  const [succeededStages, setSucceededStages] = useState<GenerationStage[]>([]);
  const [totalStages, setTotalStages] = useState<number | null>(null);
  const [error, setError] = useState<GenerationErrorEnvelope | null>(null);
  const controllerRef = useRef<AbortController | null>(null);
  const onSuccessRef = useRef(onSuccess);

  useEffect(() => {
    onSuccessRef.current = onSuccess;
  }, [onSuccess]);

  useEffect(() => {
    const controller = controllerRef.current;
    return () => controller?.abort();
  }, []);

  const handleEvent = useCallback((event: GenerationEvent) => {
    switch (event.type) {
      case "attempt.started":
        break;
      case "stage.started":
        setCurrentStage(event.stage);
        setTotalStages(event.total);
        break;
      case "stage.succeeded":
        setSucceededStages((previous) =>
          previous.includes(event.stage) ? previous : [...previous, event.stage],
        );
        setCurrentStage((previous) => (previous === event.stage ? null : previous));
        break;
      case "attempt.succeeded":
        setPhase("success");
        onSuccessRef.current?.();
        break;
      case "attempt.failed":
        setPhase("error");
        setError(event.error);
        break;
    }
  }, []);

  const begin = useCallback(() => {
    controllerRef.current?.abort();
    const controller = new AbortController();
    controllerRef.current = controller;
    setPhase("streaming");
    setError(null);
    setSucceededStages([]);
    setTotalStages(null);
    setCurrentStage(null);
    void (async () => {
      try {
        await streamGeneration({ draftId, signal: controller.signal }, handleEvent);
      } catch (cause) {
        // A newer begin() may have superseded this stream; only the current
        // controller may write terminal state.
        if (controllerRef.current !== controller) {
          return;
        }
        if (controller.signal.aborted) {
          setPhase("cancelled");
          return;
        }
        setPhase("error");
        setError({
          code: "PTS_GEN_STREAM_ERROR",
          message: cause instanceof Error ? cause.message : "生成流异常",
          retryable: true,
          requestId: "",
          recommendedAction: "",
        });
      }
    })();
  }, [draftId, handleEvent]);

  const cancel = useCallback(() => {
    controllerRef.current?.abort();
    setPhase("cancelled");
    void cancelGeneration(draftId).catch(() => undefined);
  }, [draftId]);

  return { phase, currentStage, succeededStages, totalStages, error, begin, cancel };
}
