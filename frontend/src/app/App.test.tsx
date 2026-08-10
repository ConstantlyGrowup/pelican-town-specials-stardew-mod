import "@testing-library/jest-dom/vitest";
import { render, screen } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { setupServer } from "msw/node";
import { afterAll, afterEach, beforeAll, it } from "vitest";
import { App } from "./App";
import { AppProviders } from "./providers";
import { catalogs } from "../i18n/copy";

const copy = catalogs["zh-CN"];

const server = setupServer(
  http.get("/api/v1/drafts", () =>
    HttpResponse.json({ items: [], nextCursor: null, total: 0 }),
  ),
);

beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

it("renders the home hero copy and tagline", async () => {
  render(
    <AppProviders>
      <App />
    </AppProviders>,
  );
  expect(screen.getByRole("heading", { name: copy.createFirstDraft })).toBeVisible();
  expect(screen.getByText(copy.tagline)).toBeVisible();
  // Wait for the home draft query so the component settles without act warnings.
  await screen.findByText("还没有草稿。去创建一道菜吧。");
});
