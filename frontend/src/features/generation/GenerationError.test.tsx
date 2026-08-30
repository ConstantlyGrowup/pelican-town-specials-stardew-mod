import "@testing-library/jest-dom/vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { GenerationErrorEnvelope } from "../../api/ndjson";
import { catalogs, LOCALE_STORAGE_KEY } from "../../i18n/copy";
import { LocaleProvider } from "../../i18n/locale";
import { GenerationError } from "./GenerationError";

/** The backend PTS_GEN_BUSY message is frozen in Chinese (Task 28); the
 * component must replace it with the localized limit hint, not echo it. */
const BACKEND_BUSY_MESSAGE = "当前已有一个生成任务在运行，请稍后重试。";

/** The backend PTS_TRIAL_LIMIT_REACHED message is frozen in Chinese
 * (Task 30); the component must replace it with the localized hint, not
 * echo it. */
const BACKEND_TRIAL_LIMIT_MESSAGE = "你已经达到试用额度，请配置自己的服务。";

/** The backend PTS_TRIAL_SERVICE_UNAVAILABLE message is intentionally stable
 * and redacted; the component owns the localized newcomer-facing copy. */
const BACKEND_TRIAL_SERVICE_MESSAGE =
  "试用服务失败：provider=https://hidden.example key=sk-secret；本次未消耗试用次数。";

function envelope(code: string, message: string): GenerationErrorEnvelope {
  return {
    code,
    message,
    retryable: false,
    requestId: "req-1",
    recommendedAction: "",
  };
}

beforeEach(() => {
  window.localStorage.clear();
});

describe("GenerationError", () => {
  it("shows the localized limit hint for PTS_GEN_BUSY (zh-CN default)", () => {
    render(
      <GenerationError error={envelope("PTS_GEN_BUSY", BACKEND_BUSY_MESSAGE)} />,
    );
    expect(screen.getByText(catalogs["zh-CN"].generationBusyLimit)).toBeVisible();
    // The frozen backend message is replaced, not echoed verbatim.
    expect(screen.queryByText(BACKEND_BUSY_MESSAGE)).toBeNull();
  });

  it("shows the English limit hint when the locale is en-US", () => {
    window.localStorage.setItem(LOCALE_STORAGE_KEY, "en-US");
    render(
      <LocaleProvider>
        <GenerationError
          error={envelope("PTS_GEN_BUSY", BACKEND_BUSY_MESSAGE)}
        />
      </LocaleProvider>,
    );
    expect(screen.getByText(catalogs["en-US"].generationBusyLimit)).toBeVisible();
    expect(screen.queryByText(BACKEND_BUSY_MESSAGE)).toBeNull();
  });

  it("shows the localized trial-limit hint for PTS_TRIAL_LIMIT_REACHED", () => {
    render(
      <GenerationError
        error={envelope("PTS_TRIAL_LIMIT_REACHED", BACKEND_TRIAL_LIMIT_MESSAGE)}
      />,
    );
    expect(screen.getByText(catalogs["zh-CN"].trialLimitReached)).toBeVisible();
    expect(screen.queryByText(BACKEND_TRIAL_LIMIT_MESSAGE)).toBeNull();
  });

  it("shows the English trial-limit hint when the locale is en-US", () => {
    window.localStorage.setItem(LOCALE_STORAGE_KEY, "en-US");
    render(
      <LocaleProvider>
        <GenerationError
          error={envelope("PTS_TRIAL_LIMIT_REACHED", BACKEND_TRIAL_LIMIT_MESSAGE)}
        />
      </LocaleProvider>,
    );
    expect(screen.getByText(catalogs["en-US"].trialLimitReached)).toBeVisible();
    expect(screen.queryByText(BACKEND_TRIAL_LIMIT_MESSAGE)).toBeNull();
  });

  it("shows the localized retry-safe trial service hint", () => {
    render(
      <GenerationError
        error={envelope(
          "PTS_TRIAL_SERVICE_UNAVAILABLE",
          BACKEND_TRIAL_SERVICE_MESSAGE,
        )}
      />,
    );
    expect(
      screen.getByText(catalogs["zh-CN"].trialServiceUnavailable),
    ).toBeVisible();
    expect(screen.queryByText(BACKEND_TRIAL_SERVICE_MESSAGE)).toBeNull();
    expect(screen.queryByText(/hidden\.example/)).toBeNull();
  });

  it("shows the English retry-safe trial service hint", () => {
    window.localStorage.setItem(LOCALE_STORAGE_KEY, "en-US");
    render(
      <LocaleProvider>
        <GenerationError
          error={envelope(
            "PTS_TRIAL_SERVICE_UNAVAILABLE",
            BACKEND_TRIAL_SERVICE_MESSAGE,
          )}
        />
      </LocaleProvider>,
    );
    expect(
      screen.getByText(catalogs["en-US"].trialServiceUnavailable),
    ).toBeVisible();
    expect(screen.queryByText(BACKEND_TRIAL_SERVICE_MESSAGE)).toBeNull();
  });

  it("keeps showing the backend message for non-busy codes", () => {
    render(
      <GenerationError
        error={envelope("PTS_GEN_VALIDATION_FAILED", "生成结果未通过校验。")}
      />,
    );
    expect(screen.getByText("生成结果未通过校验。")).toBeVisible();
    expect(screen.queryByText(catalogs["zh-CN"].generationBusyLimit)).toBeNull();
  });

  it("renders the retry entry only when onRetry is provided", () => {
    const onRetry = vi.fn();
    const { rerender } = render(
      <GenerationError
        error={envelope("PTS_GEN_BUSY", BACKEND_BUSY_MESSAGE)}
        onRetry={onRetry}
      />,
    );
    const retry = screen.getByRole("button", {
      name: catalogs["zh-CN"].retryGeneration,
    });
    expect(retry).toBeVisible();
    fireEvent.click(retry);
    expect(onRetry).toHaveBeenCalledTimes(1);

    rerender(
      <GenerationError error={envelope("PTS_GEN_BUSY", BACKEND_BUSY_MESSAGE)} />,
    );
    expect(
      screen.queryByRole("button", { name: catalogs["zh-CN"].retryGeneration }),
    ).toBeNull();
  });
});
