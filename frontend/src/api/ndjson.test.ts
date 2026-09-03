import { afterEach, describe, expect, it, vi } from "vitest";
import { parseChunks, streamGeneration } from "./ndjson";

afterEach(() => {
  vi.restoreAllMocks();
});

describe("parseChunks", () => {
  it("parses JSON lines split across network chunks", async () => {
    const events = await parseChunks([
      '{"type":"stage.star',
      'ted","stage":"DISH_ANALYSIS"}\n{"type":"attempt.succeeded"}\n',
    ]);
    expect(events.map((event) => event.type)).toEqual([
      "stage.started",
      "attempt.succeeded",
    ]);
  });

  it("ignores empty lines and drops the trailing residual fragment", async () => {
    const events = await parseChunks([
      '{"type":"attempt.started","attemptId":"a-1"}\n\n',
      '{"type":"stage.started","stage":"INPUT_VALIDATION","ordinal":1,"total":9}\n',
      '{"type":"stage.su',
    ]);
    expect(events.map((event) => event.type)).toEqual([
      "attempt.started",
      "stage.started",
    ]);
  });

  it("parses an ErrorEnvelope inside an attempt.failed event", async () => {
    const events = await parseChunks([
      JSON.stringify({
        type: "attempt.failed",
        attemptId: "a-1",
        error: {
          code: "PTS_GEN_VALIDATION_FAILED",
          message: "生成结果未通过校验。",
          retryable: false,
          requestId: "req-1",
          recommendedAction: "",
        },
      }) + "\n",
    ]);
    expect(events).toHaveLength(1);
    const failed = events[0];
    expect(failed.type).toBe("attempt.failed");
    if (failed.type === "attempt.failed") {
      expect(failed.error.code).toBe("PTS_GEN_VALIDATION_FAILED");
      expect(failed.error.message).toBe("生成结果未通过校验。");
    }
  });

  it("keeps only the redacted personal-provider boolean from an error envelope", async () => {
    const events = await parseChunks([
      JSON.stringify({
        type: "attempt.failed",
        attemptId: "a-1",
        error: {
          code: "PTS_TRIAL_SERVICE_UNAVAILABLE",
          message: "公共试用服务暂时不可用。",
          retryable: true,
          requestId: "req-1",
          recommendedAction: "CHECK_LOCAL_CONFIGURATION",
          details: {
            personalProviderConfigured: true,
            provider: "https://hidden.example/v1",
            apiKey: "sk-secret",
          },
        },
      }) + "\n",
    ]);

    const failed = events[0];
    expect(failed.type).toBe("attempt.failed");
    if (failed.type === "attempt.failed") {
      expect(failed.error.details).toEqual({
        personalProviderConfigured: true,
      });
      expect(JSON.stringify(failed.error)).not.toContain("hidden.example");
      expect(JSON.stringify(failed.error)).not.toContain("sk-secret");
    }
  });

  it("keeps the redacted saved-progress boolean from an error envelope", async () => {
    const events = await parseChunks([
      JSON.stringify({
        type: "attempt.failed",
        attemptId: "a-1",
        error: {
          code: "PTS_PROVIDER_UNAVAILABLE",
          message: "服务暂时不可用。",
          retryable: true,
          requestId: "req-1",
          recommendedAction: "RETRY_STAGE",
          details: {
            progressSaved: true,
            provider: "https://hidden.example/v1",
          },
        },
      }) + "\n",
    ]);

    const failed = events[0];
    expect(failed.type).toBe("attempt.failed");
    if (failed.type === "attempt.failed") {
      expect(failed.error.details).toEqual({ progressSaved: true });
      expect(JSON.stringify(failed.error)).not.toContain("hidden.example");
    }
  });
});

describe("streamGeneration", () => {
  it.each([
    { label: "by default", request: {}, expected: "" },
    { label: "when restart is false", request: { restart: false }, expected: "" },
    { label: "when restart is true", request: { restart: true }, expected: "?restart=true" },
  ])("adds the restart query only $label", async ({ request, expected }) => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response('{"type":"attempt.started","attemptId":"a-1"}\n', {
        status: 200,
        headers: { "Content-Type": "application/x-ndjson" },
      }),
    );

    await streamGeneration(
      { draftId: "draft-1", ...request },
      vi.fn(),
    );

    expect(fetchMock.mock.calls[0]?.[0]).toBe(
      `/api/v1/drafts/draft-1/generate${expected}`,
    );
  });
});
