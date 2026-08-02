import "@testing-library/jest-dom/vitest";
import { render, screen } from "@testing-library/react";
import { App } from "./App";

it("renders the frozen product name and tagline", () => {
  render(<App />);
  expect(screen.getByRole("heading", { name: "鹈鹕镇新菜单" })).toBeVisible();
  expect(screen.getByText("把你做的菜，写进鹈鹕镇的下一张菜单。")).toBeVisible();
});
