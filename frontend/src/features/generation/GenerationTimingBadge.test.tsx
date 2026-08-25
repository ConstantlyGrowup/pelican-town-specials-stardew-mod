import "@testing-library/jest-dom/vitest";
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { GenerationTimingBadge } from "./GenerationTimingBadge";

const timing = {
  startedAt: "2026-08-25T00:00:00.000Z",
  finishedAt: "2026-08-25T00:00:09.500Z",
};

describe("GenerationTimingBadge", () => {
  it("formats persisted durations below ten seconds to one decimal place", () => {
    render(<GenerationTimingBadge timing={timing} />);

    expect(screen.getByRole("status")).toHaveTextContent("9.5");
    expect(screen.getByRole("status")).toHaveAccessibleName("本次生成用时 9.5 秒");
  });

  it("rounds persisted durations of ten seconds or more to an integer", () => {
    render(
      <GenerationTimingBadge
        timing={{
          startedAt: "2026-08-25T00:00:00.000Z",
          finishedAt: "2026-08-25T00:00:12.600Z",
        }}
      />,
    );

    expect(screen.getByRole("status")).toHaveTextContent("13");
    expect(screen.getByRole("status")).not.toHaveTextContent("12.6");
  });

  it.each([
    [null, "missing timing"],
    [{ startedAt: "not-a-date", finishedAt: timing.finishedAt }, "invalid timing"],
    [
      {
        startedAt: timing.finishedAt,
        finishedAt: timing.startedAt,
      },
      "negative timing",
    ],
  ])("renders nothing for %s", (...args) => {
    const invalidTiming = args[0];
    const { container } = render(
      <GenerationTimingBadge timing={invalidTiming as typeof timing | null} />,
    );

    expect(container).toBeEmptyDOMElement();
  });

  it("uses visible Gus copy and a non-color marker for the special variant", () => {
    render(<GenerationTimingBadge timing={timing} variant="gus" />);

    expect(
      screen.getByText(
        "嗯，这道菜声名远扬，我好像在哪吃过它。于是我灵感涌现，加快了我的鉴定速度。",
      ),
    ).toBeVisible();
    expect(screen.getByText("Gus 的灵感")).toBeVisible();
    expect(screen.getByRole("status")).toHaveAttribute(
      "aria-label",
      "Gus 的灵感，本次生成用时 9.5 秒",
    );
  });
});
