import type { components } from "./generated/schema";
import { getCsrfToken } from "./client";

export type GenerationStage = components["schemas"]["GenerationStage"];

/**
 * Redacted error payload carried by `attempt.failed` NDJSON lines. Mirrors the
 * backend ErrorEnvelope shape: camelCase aliases, no secrets.
 */
export type GenerationErrorEnvelope = {
  code: string;
  message: string;
  retryable: boolean;
  requestId: string;
  recommendedAction: string;
  [key: string]: unknown;
};

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
    events.push(JSON.parse(trimmed) as GenerationEvent);
  }
  return events;
}

export type StreamGenerationRequest = {
  draftId: string;
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
  const response = await fetch(
    `/api/v1/drafts/${encodeURIComponent(request.draftId)}/generate`,
    {
      method: "POST",
      credentials: "same-origin",
      headers,
      signal: request.signal,
    },
  );
  if (!response.ok || !response.body) {
    throw new Error(`generation request failed: ${response.status}`);
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
          onEvent(JSON.parse(line) as GenerationEvent);
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
 * Cancel the draft's active generation attempt. Best-effort: the UI is already
 * back to a recoverable state by the time this resolves.
 */
export async function cancelGeneration(draftId: string): Promise<void> {
  const headers: Record<string, string> = {};
  const csrfToken = getCsrfToken();
  if (csrfToken) {
    headers["X-PTS-CSRF"] = csrfToken;
  }
  await fetch(`/api/v1/drafts/${encodeURIComponent(draftId)}/cancel`, {
    method: "POST",
    credentials: "same-origin",
    headers,
  });
}
