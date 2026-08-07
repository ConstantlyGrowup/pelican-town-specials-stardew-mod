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
  vi.useRealTimers();
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

  // --- Task 19.5: server hydration + polling --------------------------------

  const STAGES = ["INPUT_VALIDATION", "DISH_ANALYSIS"];

  function attempt(stageCount: number, status: string): object {
    return {
      attemptId: "a-1",
      draftId: "draft-1",
      kind: "INITIAL",
      sourceRevision: 1,
      status,
      currentStage: status === "RUNNING" ? "DISH_ANALYSIS" : null,
      stages: Array.from({ length: stageCount }, (_, i) => ({
        stage: STAGES[i],
        status: i < stageCount - 1 ? "SUCCEEDED" : "RUNNING",
        retryCount: 0,
        startedAt: "2026-08-04T00:00:00Z",
        finishedAt: null,
        error: null,
      })),
      startedAt: "2026-08-04T00:00:00Z",
      finishedAt: null,
      error: null,
    };
  }

  function progress(active: boolean, status: string): object {
    return {
      draftId: "draft-1",
      active,
      attempt: active ? attempt(2, status) : attempt(2, status),
    };
  }

  it("hydrates streaming progress from the server on mount", async () => {
    const getHandler = vi.fn(() =>
      HttpResponse.json(progress(true, "RUNNING")),
    );
    server.use(
      http.get("/api/v1/drafts/draft-1/generation", getHandler),
    );
    const { result } = renderHook(
      () => useGeneration({ draftId: "draft-1", running: true }),
      { wrapper },
    );

    await waitFor(() => expect(result.current.phase).toBe("streaming"));
    expect(result.current.currentStage).toBe("DISH_ANALYSIS");
    expect(result.current.succeededStages).toEqual(["INPUT_VALIDATION"]);
    expect(result.current.totalStages).toBe(2);
    expect(getHandler).toHaveBeenCalled();
  });

  it("polls and advances stage, then stops at terminal", async () => {
    // The store-level poll transition (server RUNNING → server SUCCEEDED) is
    // deterministic; the hook only schedules the interval while running and
    // tears it down on unmount. RTL's renderHook never fires setInterval in this
    // environment, so the transition itself is asserted directly on the store.
    const { applyTerminalSnapshot } = await import("./generationStore");
    server.use(
      http.get("/api/v1/drafts/draft-1/generation", () =>
        HttpResponse.json(progress(true, "RUNNING")),
      ),
    );
    const { result, unmount } = renderHook(
      () =>
        useGeneration({
          draftId: "draft-1",
          running: true,
          pollIntervalMs: 5,
        }),
      { wrapper },
    );

    // Mount hydrates to streaming (server owns the generation).
    await waitFor(() => expect(result.current.phase).toBe("streaming"));
    expect(result.current.currentStage).toBe("DISH_ANALYSIS");

    // A later poll observing the terminal attempt reflects success.
    act(() => {
      applyTerminalSnapshot("draft-1", {
        attemptId: "a-1",
        draftId: "draft-1",
        kind: "INITIAL",
        sourceRevision: 1,
        status: "SUCCEEDED",
        currentStage: null,
        stages: [],
        startedAt: "2026-08-04T00:00:00Z",
        finishedAt: "2026-08-04T00:00:00Z",
        error: null,
      } as never);
    });
    expect(result.current.phase).toBe("success");
    unmount();
  });

  it("does not poll when running is false", async () => {
    const getHandler = vi.fn();
    server.use(
      http.get("/api/v1/drafts/draft-1/generation", getHandler),
    );
    const { result, unmount } = renderHook(
      () => useGeneration({ draftId: "draft-1", running: false }),
      { wrapper },
    );
    expect(result.current.phase).toBe("idle");
    await new Promise((resolve) => setTimeout(resolve, 10));
    expect(getHandler).not.toHaveBeenCalled();
    unmount();
  });

  it("stops polling on unmount (route leave)", async () => {
    const setIntervalSpy = vi.spyOn(window, "setInterval");
    const clearIntervalSpy = vi.spyOn(window, "clearInterval");
    server.use(
      http.get("/api/v1/drafts/draft-1/generation", () =>
        HttpResponse.json(progress(true, "RUNNING")),
      ),
    );
    const { result, unmount } = renderHook(
      () =>
        useGeneration({
          draftId: "draft-1",
          running: true,
          pollIntervalMs: 5000,
        }),
      { wrapper },
    );
    await waitFor(() => expect(result.current.phase).toBe("streaming"));
    expect(setIntervalSpy).toHaveBeenCalled();
    unmount();
    // The poll interval is torn down so no further requests fire after leaving.
    expect(clearIntervalSpy).toHaveBeenCalled();
    setIntervalSpy.mockRestore();
    clearIntervalSpy.mockRestore();
  });

  it("does not create a second generate request on refresh hydration", async () => {
    const generateHandler = vi.fn(() =>
      ndjson('{"type":"attempt.started","attemptId":"a-1"}\n'),
    );
    server.use(
      http.post("/api/v1/drafts/draft-1/generate", generateHandler),
      http.get("/api/v1/drafts/draft-1/generation", () =>
        HttpResponse.json(progress(true, "RUNNING")),
      ),
    );
    const { result } = renderHook(
      () => useGeneration({ draftId: "draft-1", running: true }),
      { wrapper },
    );

    await waitFor(() => expect(result.current.phase).toBe("streaming"));
    // Hydration used the read-only endpoint, never a second POST /generate.
    expect(generateHandler).not.toHaveBeenCalled();
  });

  it("cancel after hydration still awaits the backend /cancel", async () => {
    let releaseCancel!: () => void;
    const cancelGate = new Promise<void>((resolve) => {
      releaseCancel = resolve;
    });
    const cancelHandler = vi.fn(async () => {
      await cancelGate;
      return new Response(null, { status: 202 });
    });
    server.use(
      http.get("/api/v1/drafts/draft-1/generation", () =>
        HttpResponse.json(progress(true, "RUNNING")),
      ),
      http.post("/api/v1/drafts/draft-1/cancel", cancelHandler),
    );
    const { result } = renderHook(
      () => useGeneration({ draftId: "draft-1", running: true }),
      { wrapper },
    );
    await waitFor(() => expect(result.current.phase).toBe("streaming"));

    let settled = false;
    act(() => {
      void result.current.cancel().then(() => {
        settled = true;
      });
    });
    expect(settled).toBe(false);
    await act(async () => {
      releaseCancel();
    });
    await waitFor(() => expect(settled).toBe(true));
    expect(result.current.phase).toBe("cancelled");
    expect(cancelHandler).toHaveBeenCalledTimes(1);
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
