import type { components } from "./generated/schema";
import { apiClient, getCsrfToken } from "./client";

export type GenerationStage = components["schemas"]["GenerationStage"];
export type GenerationProgress = components["schemas"]["GenerationProgressPublic"];
export type GenerationAttemptPublic =
  components["schemas"]["GenerationAttemptPublic"];

/**
 * Redacted error payload carried by `attempt.failed` NDJSON lines or a
 * non-2xx generate/cancel response body. Mirrors the backend ErrorEnvelope
 * shape: camelCase aliases, no secrets.
 */
export type GenerationErrorEnvelope = {
  code: string;
  message: string;
  retryable: boolean;
  requestId: string;
  recommendedAction: string;
  /** Only redacted boolean details cross the frontend boundary. */
  details?: {
    personalProviderConfigured?: boolean;
    progressSaved?: boolean;
  };
  [key: string]: unknown;
};

/** Raised when the generate endpoint rejects before the NDJSON stream starts. */
export class GenerationRequestError extends Error {
  readonly envelope: GenerationErrorEnvelope;

  constructor(envelope: GenerationErrorEnvelope) {
    super(envelope.message);
    this.name = "GenerationRequestError";
    this.envelope = envelope;
  }
}

/** Raised when the cancel endpoint rejects (e.g. 409 state transition). */
export class GenerationCancelError extends Error {
  readonly envelope: GenerationErrorEnvelope;

  constructor(envelope: GenerationErrorEnvelope) {
    super(envelope.message);
    this.name = "GenerationCancelError";
    this.envelope = envelope;
  }
}

function safeErrorDetails(
  value: unknown,
): GenerationErrorEnvelope["details"] | undefined {
  if (!value || typeof value !== "object") {
    return undefined;
  }
  const record = value as Record<string, unknown>;
  const details: NonNullable<GenerationErrorEnvelope["details"]> = {};
  if (typeof record.personalProviderConfigured === "boolean") {
    details.personalProviderConfigured = record.personalProviderConfigured;
  }
  if (typeof record.progressSaved === "boolean") {
    details.progressSaved = record.progressSaved;
  }
  return Object.keys(details).length > 0 ? details : undefined;
}

function sanitizeErrorEnvelope(value: unknown): GenerationErrorEnvelope {
  if (!value || typeof value !== "object") {
    return {
      code: "PTS_UNKNOWN",
      message: "Generation request failed.",
      retryable: false,
      requestId: "",
      recommendedAction: "",
    };
  }
  const record = value as Record<string, unknown>;
  const details = safeErrorDetails(record.details);
  return {
    code: typeof record.code === "string" ? record.code : "PTS_UNKNOWN",
    message:
      typeof record.message === "string"
        ? record.message
        : "Generation request failed.",
    retryable: typeof record.retryable === "boolean" ? record.retryable : false,
    requestId: typeof record.requestId === "string" ? record.requestId : "",
    recommendedAction:
      typeof record.recommendedAction === "string"
        ? record.recommendedAction
        : "",
    ...(details ? { details } : {}),
  };
}

async function parseErrorEnvelope(
  response: Response,
): Promise<GenerationErrorEnvelope> {
  let payload: unknown;
  try {
    payload = await response.json();
  } catch {
    payload = null;
  }
  const candidate =
    payload &&
    typeof payload === "object" &&
    "error" in (payload as Record<string, unknown>)
      ? (payload as { error?: unknown }).error
      : payload;
  if (candidate && typeof candidate === "object") {
    const record = candidate as Record<string, unknown>;
    if (typeof record.code === "string" && typeof record.message === "string") {
      return sanitizeErrorEnvelope(record);
    }
  }
  return {
    code: "PTS_UNKNOWN",
    message: `request failed: ${response.status}`,
    retryable: false,
    requestId: "",
    recommendedAction: "",
  };
}

/**
 * Union of the strict NDJSON generation events produced by the backend
 * (`POST /api/v1/drafts/{id}/generate`).
 */
export type GenerationEvent =
  | { type: "attempt.started"; attemptId: string }
  | {
      type: "stage.started";
      attemptId: string;
      stage: GenerationStage;
      ordinal: number;
      total: number;
    }
  | {
      type: "stage.succeeded";
      attemptId: string;
      stage: GenerationStage;
      ordinal: number;
      total: number;
    }
  | {
      type: "attempt.succeeded";
      attemptId: string;
      draftRevision: number;
      draft: Record<string, unknown>;
    }
  | { type: "attempt.failed"; attemptId: string; error: GenerationErrorEnvelope };

/**
 * Parse a set of raw network chunks into complete NDJSON events. A JSON line
 * split across chunk boundaries is joined and parsed exactly once; empty lines
 * are ignored; an unterminated trailing fragment (no terminal newline) is
 * dropped because a real stream only emits full lines.
 */
export async function parseChunks(chunks: string[]): Promise<GenerationEvent[]> {
  const joined = chunks.join("");
  const lines = joined.split("\n");
  // The final element is either "" (terminal newline) or an unterminated
  // residual fragment. Drop it in both cases.
  lines.pop();
  const events: GenerationEvent[] = [];
  for (const line of lines) {
    const trimmed = line.trim();
    if (!trimmed) {
      continue;
    }
    const parsed = JSON.parse(trimmed) as Record<string, unknown>;
    events.push(
      parsed.type === "attempt.failed"
        ? ({
            ...parsed,
            error: sanitizeErrorEnvelope(parsed.error),
          } as GenerationEvent)
        : (parsed as GenerationEvent),
    );
  }
  return events;
}

export type StreamGenerationRequest = {
  draftId: string;
  /** Explicit full regeneration; omitted/false means resume-compatible begin. */
  restart?: boolean;
  /**
   * M13 Task 59: the user's requirement for this full-regeneration round.
   * Sent as an optional JSON body; whitespace-only values are omitted so an
   * empty input keeps the historical restart behavior.
   */
  regenerationInstructions?: string;
  signal?: AbortSignal;
};

/**
 * POST the generate endpoint and consume the `application/x-ndjson` body
 * incrementally. Each fully terminated JSON line is parsed and passed to
 * `onEvent`. Uses native fetch because openapi-fetch cannot express a
 * streaming response (the OpenAPI contract types generate as application/json).
 */
export async function streamGeneration(
  request: StreamGenerationRequest,
  onEvent: (event: GenerationEvent) => void,
): Promise<void> {
  const headers: Record<string, string> = { Accept: "application/x-ndjson" };
  const csrfToken = getCsrfToken();
  if (csrfToken) {
    headers["X-PTS-CSRF"] = csrfToken;
  }
  const trimmedInstructions = request.regenerationInstructions?.trim();
  if (trimmedInstructions) {
    headers["Content-Type"] = "application/json";
  }
  const response = await fetch(
    `/api/v1/drafts/${encodeURIComponent(request.draftId)}/generate${
      request.restart === true ? "?restart=true" : ""
    }`,
    {
      method: "POST",
      credentials: "same-origin",
      headers,
      signal: request.signal,
      ...(trimmedInstructions
        ? {
            body: JSON.stringify({
              regenerationInstructions: trimmedInstructions,
            }),
          }
        : {}),
    },
  );
  if (!response.ok || !response.body) {
    throw new GenerationRequestError(await parseErrorEnvelope(response));
  }
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  try {
    for (;;) {
      const { done, value } = await reader.read();
      if (done) {
        break;
      }
      buffer += decoder.decode(value, { stream: true });
      let newline = buffer.indexOf("\n");
      while (newline >= 0) {
        const line = buffer.slice(0, newline);
        buffer = buffer.slice(newline + 1);
        if (line.trim()) {
          const parsed = JSON.parse(line) as Record<string, unknown>;
          onEvent(
            parsed.type === "attempt.failed"
              ? ({
                  ...parsed,
                  error: sanitizeErrorEnvelope(parsed.error),
                } as GenerationEvent)
              : (parsed as GenerationEvent),
          );
        }
        newline = buffer.indexOf("\n");
      }
    }
    // The backend always terminates lines with a newline, so anything left in
    // the buffer at EOF is an unterminated residual fragment: drop it.
  } finally {
    reader.releaseLock();
  }
}

/**
 * Fetch the draft's current (or most recent) generation attempt as a read-only
 * snapshot. Task 19.5: the frontend hydrates from this after a refresh / page
 * nav / reopened tab so it can re-show the server-owned generation's progress
 * instead of a blank "start generation" state.
 */
export async function fetchGenerationProgress(
  draftId: string,
): Promise<GenerationProgress> {
  const { data, error } = await apiClient.GET(
    "/api/v1/drafts/{draft_id}/generation",
    { params: { path: { draft_id: draftId } } },
  );
  if (error || !data) {
    const candidate = error as Partial<GenerationErrorEnvelope> | undefined;
    throw new GenerationRequestError(
      candidate?.code && candidate?.message
        ? (candidate as GenerationErrorEnvelope)
        : {
            code: "PTS_GEN_PROGRESS_FAILED",
            message: "无法获取生成进度。",
            retryable: true,
            requestId: "",
            recommendedAction: "",
          },
    );
  }
  return data;
}

/**
 * Cancel the draft's active generation attempt. The server rolls the draft
 * back before returning, so callers must await this before clearing local
 * stream state. A non-2xx response throws {@link GenerationCancelError} with
 * the backend's structured envelope.
 */
export async function cancelGeneration(draftId: string): Promise<void> {
  const headers: Record<string, string> = {};
  const csrfToken = getCsrfToken();
  if (csrfToken) {
    headers["X-PTS-CSRF"] = csrfToken;
  }
  const response = await fetch(
    `/api/v1/drafts/${encodeURIComponent(draftId)}/cancel`,
    {
      method: "POST",
      credentials: "same-origin",
      headers,
    },
  );
  if (!response.ok) {
    throw new GenerationCancelError(await parseErrorEnvelope(response));
  }
}
