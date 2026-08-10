import "@testing-library/jest-dom/vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import { DishSlot } from "./DishSlot";

describe("DishSlot", () => {
  it("renders an archived dish as a selected navigable slot", () => {
    render(
      <MemoryRouter>
        <DishSlot
          label="春日面碗"
          meta="主菜"
          selected
          href="/cookbook/dish-1"
        />
      </MemoryRouter>,
    );

    expect(screen.getByRole("heading", { name: "春日面碗" })).toBeVisible();
    expect(screen.getByText("主菜")).toBeVisible();
    expect(screen.getByText("✓")).toBeInTheDocument();
    expect(screen.getByRole("link")).toHaveAttribute("href", "/cookbook/dish-1");
  });

  it("renders empty slots as decorative placeholders", () => {
    render(<DishSlot label="" empty />);
    expect(screen.getByText("✣")).toBeInTheDocument();
  });

  it("renders a keyboard-accessible preview selector", () => {
    const onClick = vi.fn();
    render(
      <DishSlot
        label="菠菜烟熏三文鱼"
        meta="主菜"
        active
        onClick={onClick}
      />,
    );

    const button = screen.getByRole("button", { name: "查看菠菜烟熏三文鱼预览" });
    expect(button).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByRole("heading", { name: "菠菜烟熏三文鱼" })).toBeVisible();
    fireEvent.click(button);
    expect(onClick).toHaveBeenCalledTimes(1);
  });
});
