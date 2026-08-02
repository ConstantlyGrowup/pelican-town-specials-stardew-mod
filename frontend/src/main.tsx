import { createRoot } from "react-dom/client";
import { apiClient } from "./api/client";
import { App } from "./app/App";
import { AppProviders } from "./app/providers";

void apiClient
  .GET("/api/v1/health")
  .then(({ error }) => {
    if (error) {
      console.warn("Pelican Town Specials health probe failed", error);
    }
  })
  .catch((error: unknown) => {
    console.warn("Pelican Town Specials health probe failed", error);
  });

createRoot(document.getElementById("root")!).render(
  <AppProviders>
    <App />
  </AppProviders>,
);
