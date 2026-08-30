import { describe, expect, it } from "vitest";
import { parseChunks } from "./ndjson";

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
});
