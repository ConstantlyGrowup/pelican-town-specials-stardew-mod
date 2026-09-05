import { afterEach, describe, expect, it, vi } from "vitest";
import {
  beginGeneration,
  cancelStream,
  getGenerationState,
  resetGenerationStore,
} from "./generationStore";

function ndjson(body: string): Response {
  return new Response(body, {
    status: 200,
    headers: { "Content-Type": "application/x-ndjson" },
  });
}

const fallback = {
  streamError: "stream failed",
  cancelError: "cancel failed",
};

afterEach(() => {
  resetGenerationStore();
  vi.restoreAllMocks();
});

describe("generationStore regeneration instructions", () => {
  it("keeps the instruction when the generate request is rejected before streaming", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(
        JSON.stringify({
          error: {
            code: "PTS_STATE_ILLEGAL_TRANSITION",
            message: "busy",
            retryable: true,
            requestId: "r-1",
            recommendedAction: "",
          },
        }),
        { status: 409, headers: { "Content-Type": "application/json" } },
      ),
    );

    beginGeneration("draft-1", undefined, fallback, {
      restart: false,
      regenerationInstructions: "鱼片切厚一点",
    });

    await vi.waitFor(() =>
      expect(getGenerationState("draft-1").phase).toBe("error"),
    );
    expect(getGenerationState("draft-1").regenerationInstructions).toBe(
      "鱼片切厚一点",
    );
  });

  it("keeps the instruction after a network failure and cancellation", async () => {
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockRejectedValueOnce(new TypeError("offline"))
      .mockResolvedValueOnce(new Response(null, { status: 202 }));

    beginGeneration("draft-1", undefined, fallback, {
      restart: false,
      regenerationInstructions: "摆成扇形",
    });
    await vi.waitFor(() =>
      expect(getGenerationState("draft-1").phase).toBe("error"),
    );
    expect(getGenerationState("draft-1").regenerationInstructions).toBe(
      "摆成扇形",
    );

    await cancelStream("draft-1", fallback);

    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(getGenerationState("draft-1").phase).toBe("cancelled");
    expect(getGenerationState("draft-1").regenerationInstructions).toBe(
      "摆成扇形",
    );
  });

  it("clears the instruction only after the round succeeds", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      ndjson(
        '{"type":"attempt.started","attemptId":"a-1"}\n' +
          '{"type":"attempt.succeeded","attemptId":"a-1","draftRevision":4,"draft":{}}\n',
      ),
    );

    beginGeneration("draft-1", undefined, fallback, {
      restart: true,
      regenerationInstructions: "鱼片切厚一点",
    });

    await vi.waitFor(() =>
      expect(getGenerationState("draft-1").phase).toBe("success"),
    );
    expect(getGenerationState("draft-1").regenerationInstructions).toBe("");
  });
});
