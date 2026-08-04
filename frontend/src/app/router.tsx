import { useQuery } from "@tanstack/react-query";
import { Route, Routes, useParams } from "react-router-dom";
import { apiClient } from "../api/client";
import type { components } from "../api/generated/schema";
import { CreateDishPage } from "../features/create/CreateDishPage";
import { CookbookDetailPage } from "../features/cookbook/CookbookDetailPage";
import { CookbookPage } from "../features/cookbook/CookbookPage";
import { AskGusReviewPage } from "../features/draft/AskGusReviewPage";
import { BlueprintEditorPage } from "../features/draft/BlueprintEditorPage";
import { SettingsPage } from "../features/settings/SettingsPage";
import { PRODUCT_COPY } from "../i18n/copy";
import { AppShell } from "./layout/AppShell";

type DraftView = components["schemas"]["DraftView"];

/**
 * Loads the draft once and dispatches by mode: ASK_GUS drafts render the Ask
 * Gus review page, BLUEPRINT drafts render the Blueprint editor. The query key
 * is shared with both pages so the fetched draft is reused, not fetched twice.
 */
function DraftRoute() {
  const { draftId } = useParams<{ draftId: string }>();
  const copy = PRODUCT_COPY.zh;
  const query = useQuery({
    queryKey: ["draft", draftId],
    queryFn: async (): Promise<DraftView> => {
      const { data, error } = await apiClient.GET("/api/v1/drafts/{draft_id}", {
        params: { path: { draft_id: draftId ?? "" } },
      });
      if (error || !data) {
        throw new Error("load failed");
      }
      return data;
    },
    enabled: Boolean(draftId),
  });

  if (query.isLoading) {
    return (
      <main>
        <h1>{copy.draftTitle}</h1>
        <p>{copy.loading}</p>
      </main>
    );
  }

  if (query.isError || !query.data) {
    return (
      <main>
        <h1>{copy.draftNotFound}</h1>
      </main>
    );
  }

  return query.data.mode === "ASK_GUS" ? <AskGusReviewPage /> : <BlueprintEditorPage />;
}

export function AppRouter() {
  const copy = PRODUCT_COPY.zh;

  return (
    <Routes>
      <Route element={<AppShell />}>
        <Route
          index
          element={
            <main aria-labelledby="app-title">
              <p lang="en">Pelican Town Specials</p>
              <h1 id="app-title">{copy.productName}</h1>
              <p>{copy.tagline}</p>
            </main>
          }
        />
        <Route path="settings" element={<SettingsPage />} />
        <Route path="create" element={<CreateDishPage />} />
        <Route path="drafts/:draftId" element={<DraftRoute />} />
        <Route path="cookbook" element={<CookbookPage />} />
        <Route path="cookbook/:dishId" element={<CookbookDetailPage />} />
        <Route
          path="*"
          element={
            <main>
              <h1>{copy.notFoundTitle}</h1>
              <p>{copy.notFoundMessage}</p>
            </main>
          }
        />
      </Route>
    </Routes>
  );
}
