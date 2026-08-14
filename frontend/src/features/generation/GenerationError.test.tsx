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
