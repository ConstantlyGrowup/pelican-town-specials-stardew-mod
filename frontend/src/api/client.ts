import createClient, { type Middleware } from "openapi-fetch";
import type { paths } from "./generated/schema";

let csrfToken: string | null = null;

export function getCsrfToken(): string | null {
  return csrfToken;
}

export function assetUrl(assetId: string | null | undefined): string | null {
  if (!assetId) {
    return null;
  }
  return `/api/v1/assets/${encodeURIComponent(assetId)}`;
}

export async function bootstrapSession(launchToken: string): Promise<string> {
  csrfToken = null;
  const response = await fetch("/session/bootstrap", {
    method: "POST",
    credentials: "same-origin",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ launchToken }),
  });
  const responseToken = response.headers.get("X-PTS-CSRF");
  if (response.status !== 204 || !responseToken) {
    throw new Error("Local session bootstrap failed");
  }
  csrfToken = responseToken;
  return responseToken;
}

/**
 * Recover the CSRF token for an existing session after a page reload. The
 * token lives only in browser memory, so reloads lose it while the HttpOnly
 * session cookie persists; this endpoint re-issues it to the session holder.
 */
export async function restoreSession(): Promise<string | null> {
  try {
    const response = await fetch("/session/status", {
      credentials: "same-origin",
    });
    const responseToken = response.headers.get("X-PTS-CSRF");
    if (response.status === 200 && responseToken) {
      csrfToken = responseToken;
      return responseToken;
    }
    csrfToken = null;
    return null;
  } catch {
    csrfToken = null;
    return null;
  }
}

export function clearLaunchFragment(location: Location, history: History): void {
  if (!location.hash.startsWith("#launch=")) {
    return;
  }
  history.replaceState(history.state, "", `${location.pathname}${location.search}`);
}

export async function sendHeartbeat(): Promise<void> {
  if (!csrfToken) {
    return;
  }
  try {
    await fetch("/app/heartbeat", {
      method: "POST",
      credentials: "same-origin",
      headers: {
        "X-PTS-CSRF": csrfToken,
      },
    });
  } catch {
    // A later heartbeat can recover a transient local connection failure.
  }
}

export function startHeartbeat(): () => void {
  if (!csrfToken || typeof window === "undefined") {
    return () => undefined;
  }
  const intervalId = window.setInterval(() => {
    void sendHeartbeat();
  }, 30_000);
  const cleanup = () => {
    window.clearInterval(intervalId);
    window.removeEventListener("pagehide", cleanup);
  };
  window.addEventListener("pagehide", cleanup, { once: true });
  return cleanup;
}

export function addCsrfToRequest(request: Request): Request | undefined {
  if (request.method === "GET") {
    return;
  }
  const currentLocation = typeof window === "undefined" ? undefined : window.location;
  if (!currentLocation) {
    return;
  }
  const requestOrigin = new URL(request.url, currentLocation.href).origin;
  if (requestOrigin !== currentLocation.origin) {
    return;
  }
  const headers = new Headers(request.headers);
  if (csrfToken) {
    headers.set("X-PTS-CSRF", csrfToken);
  }
  return new Request(request, {
    credentials: "same-origin",
    headers,
  });
}

const csrfMiddleware: Middleware = {
  onRequest({ request }) {
    return addCsrfToRequest(request);
  },
};

const sameOriginBaseUrl =
  typeof window === "undefined" ? "" : window.location.origin;

export const apiClient = createClient<paths>({
  baseUrl: sameOriginBaseUrl,
  // Resolve fetch at request time so test MSW interception is honored; the
  // browser global is stable, so production behavior is unchanged.
  fetch: (input: RequestInfo | URL, init?: RequestInit) =>
    globalThis.fetch(input, init),
});

apiClient.use(csrfMiddleware);
