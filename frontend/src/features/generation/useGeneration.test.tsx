import "@testing-library/jest-dom/vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { setupServer } from "msw/node";
import type { PropsWithChildren } from "react";
import { afterAll, afterEach, beforeAll, describe, expect, it, vi } from "vitest";
import { resetGenerationStore } from "./generationStore";
import { useGeneration } from "./useGeneration";

const server = setupServer();

function wrapper({ children }: PropsWithChildren) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
}

function ndjson(body: string) {
  return new Response(body, {
    status: 200,
    headers: { "Content-Type": "application/x-ndjson" },
  });
}

beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
afterEach(() => {
  server.resetHandlers();
  resetGenerationStore();
});
afterAll(() => server.close());

describe("useGeneration", () => {
  it("streams to success and calls onSuccess", async () => {
    const onSuccess = vi.fn();
    server.use(
      http.post("/api/v1/drafts/:draft_id/generate", () =>
        ndjson(
          '{"type":"attempt.started","attemptId":"a-1"}\n' +
            '{"type":"attempt.succeeded","attemptId":"a-1","draftRevision":3,"draft":{}}\n',
        ),
      ),
    );
    const { result } = renderHook(
      () => useGeneration({ draftId: "draft-1", onSuccess }),
      { wrapper },
    );

    act(() => result.current.begin());

    await waitFor(() => expect(result.current.phase).toBe("success"));
    expect(onSuccess).toHaveBeenCalledTimes(1);
  });

  it("surfaces the backend envelope on a 409 generate rejection", async () => {
    server.use(
      http.post("/api/v1/drafts/:draft_id/generate", () =>
        HttpResponse.json(
          {
            error: {
              code: "PTS_GEN_BUSY",
              message: "当前已有一个生成任务在运行。",
              retryable: false,
              requestId: "req-1",
              recommendedAction: "",
            },
          },
          { status: 409 },
        ),
      ),
    );
    const { result } = renderHook(() => useGeneration({ draftId: "draft-1" }), {
      wrapper,
    });

    act(() => result.current.begin());

    await waitFor(() => expect(result.current.phase).toBe("error"));
    expect(result.current.error?.code).toBe("PTS_GEN_BUSY");
    expect(result.current.error?.message).toBe("当前已有一个生成任务在运行。");
  });

  it("awaits the backend cancel before clearing streaming state", async () => {
    let releaseCancel!: () => void;
    const cancelGate = new Promise<void>((resolve) => {
      releaseCancel = resolve;
    });
    server.use(
      http.post("/api/v1/drafts/:draft_id/generate", () =>
        ndjson('{"type":"attempt.started","attemptId":"a-1"}\n'),
      ),
      http.post("/api/v1/drafts/:draft_id/cancel", async () => {
        await cancelGate;
        return new Response(null, { status: 202 });
      }),
    );
    const { result } = renderHook(() => useGeneration({ draftId: "draft-1" }), {
      wrapper,
    });
    act(() => result.current.begin());
    await waitFor(() => expect(result.current.phase).toBe("streaming"));

    let settled = false;
    act(() => {
      void result.current.cancel().then(() => {
        settled = true;
      });
    });

    // The stream stays visible until the backend /cancel resolves.
    expect(settled).toBe(false);
    expect(result.current.phase).toBe("streaming");

    await act(async () => {
      releaseCancel();
    });
    await waitFor(() => expect(settled).toBe(true));
    expect(result.current.phase).toBe("cancelled");
  });

  it("surfaces the backend envelope when cancel is rejected", async () => {
    server.use(
      http.post("/api/v1/drafts/:draft_id/generate", () =>
        ndjson('{"type":"attempt.started","attemptId":"a-1"}\n'),
      ),
      http.post("/api/v1/drafts/:draft_id/cancel", () =>
        HttpResponse.json(
          {
            error: {
              code: "PTS_STATE_ILLEGAL_TRANSITION",
              message: "草稿当前状态不允许该操作。",
              retryable: false,
              requestId: "req-1",
              recommendedAction: "",
            },
          },
          { status: 409 },
        ),
      ),
    );
    const { result } = renderHook(() => useGeneration({ draftId: "draft-1" }), {
      wrapper,
    });
    act(() => result.current.begin());
    await waitFor(() => expect(result.current.phase).toBe("streaming"));

    await act(async () => {
      await result.current.cancel();
    });

    expect(result.current.phase).toBe("error");
    expect(result.current.error?.code).toBe("PTS_STATE_ILLEGAL_TRANSITION");
  });

  it("restores streaming progress after unmount and remount", async () => {
    server.use(
      http.post("/api/v1/drafts/:draft_id/generate", () =>
        ndjson(
          '{"type":"attempt.started","attemptId":"a-1"}\n' +
            '{"type":"stage.started","stage":"DISH_ANALYSIS","ordinal":2,"total":9}\n',
        ),
      ),
    );
    const first = renderHook(() => useGeneration({ draftId: "draft-1" }), {
      wrapper,
    });
    act(() => first.result.current.begin());
    await waitFor(() =>
      expect(first.result.current.currentStage).toBe("DISH_ANALYSIS"),
    );
    first.unmount();

    const second = renderHook(() => useGeneration({ draftId: "draft-1" }), {
      wrapper,
    });
    expect(second.result.current.phase).toBe("streaming");
    expect(second.result.current.currentStage).toBe("DISH_ANALYSIS");
    expect(second.result.current.totalStages).toBe(9);
    second.unmount();
  });

  it("does not let a stale cancel abort or cancel a newer generation", async () => {
    let releaseCancel!: () => void;
    const cancelGate = new Promise<void>((resolve) => {
      releaseCancel = resolve;
    });
    const generateHandler = vi.fn();
    const cancelHandler = vi.fn();
    server.use(
      http.post("/api/v1/drafts/:draft_id/generate", () => {
        generateHandler();
        return ndjson('{"type":"attempt.started","attemptId":"a-1"}\n');
      }),
      http.post("/api/v1/drafts/:draft_id/cancel", async () => {
        cancelHandler();
        await cancelGate;
        return new Response(null, { status: 202 });
      }),
    );
    const { result } = renderHook(() => useGeneration({ draftId: "draft-1" }), {
      wrapper,
    });
    act(() => result.current.begin());
    await waitFor(() => expect(result.current.phase).toBe("streaming"));

    let firstSettled = false;
    act(() => {
      void result.current.cancel().then(() => {
        firstSettled = true;
      });
    });
    expect(firstSettled).toBe(false);

    // A new generation begins while the first cancel is still pending; the new
    // round swaps in a fresh controller.
    act(() => result.current.begin());
    expect(result.current.phase).toBe("streaming");

    // Release the stale cancel. Its finally must not abort the new controller
    // or mark the new round as cancelled.
    await act(async () => {
      releaseCancel();
    });
    await waitFor(() => expect(firstSettled).toBe(true));

    expect(generateHandler).toHaveBeenCalledTimes(2);
    expect(cancelHandler).toHaveBeenCalledTimes(1);
    expect(result.current.phase).toBe("streaming");
  });

  it("deduplicates concurrent cancels per draft (single-flight)", async () => {
    let releaseCancel!: () => void;
    const cancelGate = new Promise<void>((resolve) => {
      releaseCancel = resolve;
    });
    const cancelHandler = vi.fn();
    server.use(
      http.post("/api/v1/drafts/:draft_id/generate", () =>
        ndjson('{"type":"attempt.started","attemptId":"a-1"}\n'),
      ),
      http.post("/api/v1/drafts/:draft_id/cancel", async () => {
        cancelHandler();
        await cancelGate;
        return new Response(null, { status: 202 });
      }),
    );
    const { result } = renderHook(() => useGeneration({ draftId: "draft-1" }), {
      wrapper,
    });
    act(() => result.current.begin());
    await waitFor(() => expect(result.current.phase).toBe("streaming"));

    let firstSettled = false;
    let secondSettled = false;
    act(() => {
      void result.current.cancel().then(() => {
        firstSettled = true;
      });
      void result.current.cancel().then(() => {
        secondSettled = true;
      });
    });

    // Single-flight: the second cancel reuses the first operation's promise,
    // so only one /cancel request reaches the server.
    await waitFor(() => expect(cancelHandler).toHaveBeenCalledTimes(1));
    expect(firstSettled).toBe(false);
    expect(secondSettled).toBe(false);

    await act(async () => {
      releaseCancel();
    });
    await waitFor(() => expect(firstSettled).toBe(true));
    await waitFor(() => expect(secondSettled).toBe(true));
    expect(cancelHandler).toHaveBeenCalledTimes(1);
    expect(result.current.phase).toBe("cancelled");
  });
});
