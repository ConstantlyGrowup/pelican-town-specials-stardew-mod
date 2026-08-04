import "@testing-library/jest-dom/vitest";
import { render, screen } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { setupServer } from "msw/node";
import { afterAll, afterEach, beforeAll, it } from "vitest";
import { App } from "./App";
import { AppProviders } from "./providers";

const server = setupServer(
  http.get("/api/v1/drafts", () =>
    HttpResponse.json({ items: [], nextCursor: null, total: 0 }),
  ),
);

beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

it("renders the frozen product name and tagline", async () => {
  render(
    <AppProviders>
      <App />
    </AppProviders>,
  );
  expect(screen.getByRole("heading", { name: "鹈鹕镇新菜单" })).toBeVisible();
  expect(screen.getByText("把你做的菜，写进鹈鹕镇的下一张菜单。")).toBeVisible();
  // Wait for the home draft query so the component settles without act warnings.
  await screen.findByText("还没有草稿。去创建一道菜吧。");
});
