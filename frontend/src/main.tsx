import "./styles/global.css";
import { createRoot } from "react-dom/client";
import {
  apiClient,
  bootstrapSession,
  clearLaunchFragment,
  restoreSession,
  startHeartbeat,
} from "./api/client";
import { App } from "./app/App";
import { AppProviders } from "./app/providers";

function launchTokenFromLocation(location: Location): string | null {
  if (!location.hash.startsWith("#launch=")) {
    return null;
  }
  const encodedToken = location.hash.slice("#launch=".length);
  if (!encodedToken) {
    return null;
  }
  try {
    return decodeURIComponent(encodedToken);
  } catch {
    return encodedToken;
  }
}

export async function bootstrapAndProbe(
  location: Location = window.location,
  history: History = window.history,
): Promise<void> {
  const launchToken = launchTokenFromLocation(location);
  if (launchToken) {
    try {
      await bootstrapSession(launchToken);
      clearLaunchFragment(location, history);
    } catch {
      console.warn("Pelican Town Specials session bootstrap failed");
    }
  }
  // Recover the in-memory CSRF token after a reload so existing mutations do
  // not fail with PTS_AUTH_CSRF_INVALID. No-op when there is no session.
  await restoreSession();

  try {
    const { error } = await apiClient.GET("/api/v1/health");
    if (error) {
      console.warn("Pelican Town Specials health probe failed");
    }
  } catch {
    console.warn("Pelican Town Specials health probe failed");
  }
}

const rootElement = document.getElementById("root");
if (rootElement) {
  void bootstrapAndProbe().then(() => {
    startHeartbeat();
  });
  createRoot(rootElement).render(
    <AppProviders>
      <App />
    </AppProviders>,
  );
}