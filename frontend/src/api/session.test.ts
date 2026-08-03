import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

type SessionModule = typeof import("./client");

function launchLocation(hash: string): Location {
  return {
    hash,
    pathname: "/",
    search: "",
  } as Location;
}

async function loadSessionModule(fetchStub: ReturnType<typeof vi.fn>): Promise<SessionModule> {
  vi.stubGlobal("fetch", fetchStub);
  return import("./client");
}

describe("local launch session", () => {
  beforeEach(() => {
    vi.resetModules();
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it("posts the launch token with same-origin credentials and stores the returned CSRF value", async () => {
    const fetchStub = vi.fn().mockResolvedValue(
      new Response(null, {
        status: 204,
        headers: { "X-PTS-CSRF": "csrf-from-server" },
      }),
    );
    const { bootstrapSession } = await loadSessionModule(fetchStub);

    await expect(bootstrapSession("launch-token")).resolves.toBe("csrf-from-server");

    expect(fetchStub).toHaveBeenCalledWith(
      "/session/bootstrap",
      expect.objectContaining({
        body: JSON.stringify({ launchToken: "launch-token" }),
        credentials: "same-origin",
        method: "POST",
      }),
    );
  });

  it("rejects a bootstrap response without the expected status and CSRF header", async () => {
    const fetchStub = vi.fn().mockResolvedValue(new Response(null, { status: 200 }));
    const { bootstrapSession } = await loadSessionModule(fetchStub);

    await expect(bootstrapSession("launch-token")).rejects.toThrow("Local session bootstrap failed");
  });

  it("clears only a successful launch fragment while preserving the page path and query", async () => {
    const fetchStub = vi.fn();
    const { clearLaunchFragment } = await loadSessionModule(fetchStub);
    const replaceState = vi.fn();
    const history = { replaceState, state: { source: "test" } } as unknown as History;
    const location = {
      hash: "#launch=launch-token",
      pathname: "/cookbook",
      search: "?tab=drafts",
    } as Location;

    clearLaunchFragment(location, history);

    expect(replaceState).toHaveBeenCalledWith({ source: "test" }, "", "/cookbook?tab=drafts");
  });

  it("adds the in-memory CSRF value to same-origin mutations without dropping existing headers", async () => {
    const fetchStub = vi
      .fn()
      .mockResolvedValueOnce(
        new Response(null, {
          status: 204,
          headers: { "X-PTS-CSRF": "csrf-from-server" },
        }),
      )
      .mockResolvedValueOnce(new Response(null, { status: 204 }));
    const { apiClient, bootstrapSession } = await loadSessionModule(fetchStub);

    await bootstrapSession("launch-token");
    fetchStub.mockClear();
    await (apiClient as unknown as { request: (method: string, path: string, init?: unknown) => Promise<unknown> }).request(
      "POST",
      "/api/v1/settings",
      { headers: { "X-Existing": "kept" } },
    );

    const request = fetchStub.mock.calls[0]?.[0] as Request;
    expect(request.credentials).toBe("same-origin");
    expect(request.headers.get("X-Existing")).toBe("kept");
    expect(request.headers.get("X-PTS-CSRF")).toBe("csrf-from-server");
  });

  it("does not attach CSRF to a cross-origin mutation", async () => {
    const fetchStub = vi
      .fn()
      .mockResolvedValueOnce(
        new Response(null, {
          status: 204,
          headers: { "X-PTS-CSRF": "csrf-from-server" },
        }),
      )
      .mockResolvedValueOnce(new Response(null, { status: 204 }));
    const { addCsrfToRequest, bootstrapSession } = await loadSessionModule(fetchStub);

    await bootstrapSession("launch-token");
    const request = addCsrfToRequest(
      new Request("https://other.example/api/v1/settings", { method: "POST" }),
    );
    expect(request).toBeUndefined();
  });

  it("sends a CSRF-protected heartbeat every 30 seconds and cleans it up", async () => {
    const fetchStub = vi.fn().mockResolvedValue(
      new Response(null, {
        status: 204,
        headers: { "X-PTS-CSRF": "csrf-from-server" },
      }),
    );
    const { bootstrapSession, startHeartbeat } = await loadSessionModule(fetchStub);
    await bootstrapSession("launch-token");

    const setInterval = vi.spyOn(window, "setInterval");
    const clearInterval = vi.spyOn(window, "clearInterval");
    const addEventListener = vi.spyOn(window, "addEventListener");
    const removeEventListener = vi.spyOn(window, "removeEventListener");
    setInterval.mockReturnValue(42 as unknown as ReturnType<typeof setInterval>);

    const cleanup = startHeartbeat();
    const heartbeat = setInterval.mock.calls[0]?.[0] as () => void;
    heartbeat();
    await Promise.resolve();

    expect(setInterval).toHaveBeenCalledWith(expect.any(Function), 30_000);
    expect(fetchStub).toHaveBeenLastCalledWith(
      "/app/heartbeat",
      expect.objectContaining({
        credentials: "same-origin",
        headers: { "X-PTS-CSRF": "csrf-from-server" },
        method: "POST",
      }),
    );
    expect(addEventListener).toHaveBeenCalledWith("pagehide", expect.any(Function), {
      once: true,
    });

    cleanup();
    expect(clearInterval).toHaveBeenCalledWith(42);
    expect(removeEventListener).toHaveBeenCalledWith("pagehide", expect.any(Function));
  });
  it("bootstraps a launch fragment before the existing health probe", async () => {
    const fetchStub = vi
      .fn()
      .mockResolvedValueOnce(
        new Response(null, {
          status: 204,
          headers: { "X-PTS-CSRF": "csrf-from-server" },
        }),
      )
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ status: "ok", app: "PelicanTownSpecials", apiVersion: "v1" }), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        }),
      );
    vi.stubGlobal("fetch", fetchStub);
    const { bootstrapAndProbe } = await import("../main");
    const replaceState = vi.fn();
    const history = { replaceState, state: null } as unknown as History;

    await bootstrapAndProbe(launchLocation("#launch=launch-token"), history);

    expect(fetchStub.mock.calls[0]?.[0]).toBe("/session/bootstrap");
    expect((fetchStub.mock.calls[1]?.[0] as Request).url).toContain("/api/v1/health");
    expect(replaceState).toHaveBeenCalledTimes(1);
  });

  it("keeps the existing health probe when there is no launch fragment", async () => {
    const fetchStub = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ status: "ok", app: "PelicanTownSpecials", apiVersion: "v1" }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );
    vi.stubGlobal("fetch", fetchStub);
    const { bootstrapAndProbe } = await import("../main");
    const replaceState = vi.fn();

    await bootstrapAndProbe(launchLocation(""), { replaceState, state: null } as unknown as History);

    expect(fetchStub).toHaveBeenCalledTimes(1);
    expect((fetchStub.mock.calls[0]?.[0] as Request).url).toContain("/api/v1/health");
    expect(replaceState).not.toHaveBeenCalled();
  });
});
