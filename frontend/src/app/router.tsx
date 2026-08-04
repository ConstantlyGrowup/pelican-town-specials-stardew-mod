import { Route, Routes } from "react-router-dom";
import { CreateDishPage } from "../features/create/CreateDishPage";
import { CookbookDetailPage } from "../features/cookbook/CookbookDetailPage";
import { CookbookPage } from "../features/cookbook/CookbookPage";
import { BlueprintEditorPage } from "../features/draft/BlueprintEditorPage";
import { SettingsPage } from "../features/settings/SettingsPage";
import { PRODUCT_COPY } from "../i18n/copy";
import { AppShell } from "./layout/AppShell";

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
        <Route path="drafts/:draftId" element={<BlueprintEditorPage />} />
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
