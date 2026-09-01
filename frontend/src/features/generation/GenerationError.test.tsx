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

function envelope(
  code: string,
  message: string,
  details?: GenerationErrorEnvelope["details"],
): GenerationErrorEnvelope {
  return {
    code,
    message,
    retryable: false,
    requestId: "req-1",
    recommendedAction: "",
    ...(details ? { details } : {}),
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

  it("shows the English trial service hint with an immediate retry action", () => {
    const onRetry = vi.fn();
    window.localStorage.setItem(LOCALE_STORAGE_KEY, "en-US");
    render(
      <LocaleProvider>
        <GenerationError
          error={envelope(
            "PTS_TRIAL_SERVICE_UNAVAILABLE",
            BACKEND_TRIAL_SERVICE_MESSAGE,
          )}
          onRetry={onRetry}
        />
      </LocaleProvider>,
    );
    expect(
      screen.getByText(catalogs["en-US"].trialServiceUnavailable),
    ).toBeVisible();
    expect(screen.queryByText(BACKEND_TRIAL_SERVICE_MESSAGE)).toBeNull();
    const retry = screen.getByRole("button", {
      name: catalogs["en-US"].retryNow,
    });
    expect(retry).toBeVisible();
    fireEvent.click(retry);
    expect(onRetry).toHaveBeenCalledTimes(1);
  });

  it("localizes the discard action and gates it to trial service errors", () => {
    const onDiscard = vi.fn();
    window.localStorage.setItem(LOCALE_STORAGE_KEY, "en-US");
    const { rerender } = render(
      <LocaleProvider>
        <GenerationError
          error={envelope(
            "PTS_TRIAL_SERVICE_UNAVAILABLE",
            BACKEND_TRIAL_SERVICE_MESSAGE,
          )}
          onDiscard={onDiscard}
        />
      </LocaleProvider>,
    );

    const discard = screen.getByRole("button", {
      name: catalogs["en-US"].discardDraftAndReturnHome,
    });
    expect(discard).toBeVisible();
    fireEvent.click(discard);
    expect(onDiscard).toHaveBeenCalledTimes(1);

    rerender(
      <LocaleProvider>
        <GenerationError
          error={envelope("PTS_GEN_VALIDATION_FAILED", "生成结果未通过校验。")}
          onDiscard={onDiscard}
        />
      </LocaleProvider>,
    );
    expect(
      screen.queryByRole("button", {
        name: catalogs["en-US"].discardDraftAndReturnHome,
      }),
    ).toBeNull();
  });

  it("keeps showing the backend message for unknown codes", () => {
    render(
      <GenerationError
        error={envelope("PTS_UNKNOWN_CODE", "未知错误，仅用于诊断。")}
      />,
    );
    expect(screen.getByText("未知错误，仅用于诊断。")).toBeVisible();
    expect(screen.queryByText(catalogs["zh-CN"].generationBusyLimit)).toBeNull();
  });

  it("shows the fixed zh-CN backend phrasing for mapped generation codes", () => {
    render(
      <GenerationError
        error={envelope("PTS_GEN_VALIDATION_FAILED", "生成结果未通过校验。")}
      />,
    );
    expect(screen.getByText(catalogs["zh-CN"].errGenerationValidationFailed)).toBeVisible();
  });

  it("shows English copy instead of the Chinese backend message for mapped codes", () => {
    window.localStorage.setItem(LOCALE_STORAGE_KEY, "en-US");
    render(
      <LocaleProvider>
        <GenerationError
          error={envelope("PTS_GEN_LOW_CONFIDENCE", "图片识别置信度过低，请换一张更清晰的照片。")}
        />
      </LocaleProvider>,
    );
    expect(screen.getByText(catalogs["en-US"].errLowConfidence)).toBeVisible();
    expect(screen.queryByText(/置信度过低/)).toBeNull();
  });

  it("shows the English provider-key hint instead of the Chinese backend message", () => {
    window.localStorage.setItem(LOCALE_STORAGE_KEY, "en-US");
    render(
      <LocaleProvider>
        <GenerationError
          error={envelope("PTS_PROVIDER_AUTH_FAILED", "Provider Key 无效或未授权。")}
        />
      </LocaleProvider>,
    );
    expect(screen.getByText(catalogs["en-US"].errProviderAuthFailed)).toBeVisible();
    expect(screen.queryByText(/Provider Key 无效或未授权/)).toBeNull();
  });

  it("keeps the zh-CN backend wording for variable provider messages", () => {
    render(
      <GenerationError
        error={envelope("PTS_PROVIDER_AUTH_FAILED", "Provider Key 未配置。")}
      />,
    );
    expect(screen.getByText("Provider Key 未配置。")).toBeVisible();
    expect(screen.queryByText(catalogs["zh-CN"].errProviderAuthFailed)).toBeNull();
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

  it("offers personal takeover and an immediate retry when personal service is configured", () => {
    const onTakeover = vi.fn();
    const onRetry = vi.fn();
    render(
      <GenerationError
        error={envelope(
          "PTS_TRIAL_SERVICE_UNAVAILABLE",
          BACKEND_TRIAL_SERVICE_MESSAGE,
          { personalProviderConfigured: true },
        )}
        onTakeover={onTakeover}
        onRetry={onRetry}
      />,
    );

    fireEvent.click(
      screen.getByRole("button", { name: catalogs["zh-CN"].usePersonalProvider }),
    );
    fireEvent.click(
      screen.getByRole("button", { name: catalogs["zh-CN"].retryNow }),
    );
    expect(onTakeover).toHaveBeenCalledTimes(1);
    expect(onRetry).toHaveBeenCalledTimes(1);
  });

  it("offers configuration when the personal service is not configured or the trial is exhausted", () => {
    const onConfigure = vi.fn();
    const { rerender } = render(
      <GenerationError
        error={envelope(
          "PTS_TRIAL_SERVICE_UNAVAILABLE",
          BACKEND_TRIAL_SERVICE_MESSAGE,
          { personalProviderConfigured: false },
        )}
        onConfigure={onConfigure}
      />,
    );

    expect(
      screen.getByRole("button", {
        name: catalogs["zh-CN"].configurePersonalProvider,
      }),
    ).toBeVisible();
    fireEvent.click(
      screen.getByRole("button", {
        name: catalogs["zh-CN"].configurePersonalProvider,
      }),
    );
    expect(onConfigure).toHaveBeenCalledTimes(1);

    rerender(
      <GenerationError
        error={envelope("PTS_TRIAL_LIMIT_REACHED", BACKEND_TRIAL_LIMIT_MESSAGE)}
        onConfigure={onConfigure}
      />,
    );
    expect(
      screen.getByRole("button", {
        name: catalogs["zh-CN"].configurePersonalProvider,
      }),
    ).toBeVisible();
  });
});
