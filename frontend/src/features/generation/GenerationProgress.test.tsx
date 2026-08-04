import "@testing-library/jest-dom/vitest";
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { PRODUCT_COPY } from "../../i18n/copy";
import { GenerationProgress } from "./GenerationProgress";

const copy = PRODUCT_COPY.zh;

describe("GenerationProgress", () => {
  it("shows the preparing banner and the current stage label", () => {
    render(
      <GenerationProgress
        currentStage="DISH_ANALYSIS"
        succeededStages={["INPUT_VALIDATION"]}
        totalStages={9}
        preparingLabel={copy.preparingNewResult}
      />,
    );
    expect(screen.getByText(copy.preparingNewResult)).toBeVisible();
    expect(screen.getByText(copy.generationStageLabels.DISH_ANALYSIS)).toBeVisible();
  });

  it("shows a completed count derived only from real stage events", () => {
    render(
      <GenerationProgress
        currentStage="GAMEPLAY_DESIGN"
        succeededStages={["INPUT_VALIDATION", "DISH_ANALYSIS"]}
        totalStages={9}
      />,
    );
    const expected = copy.stagesCompleted
      .replace("{succeeded}", "2")
      .replace("{total}", "9");
    expect(screen.getByText(expected)).toBeVisible();
  });

  it("offers a cancel control when onCancel is provided", () => {
    const onCancel = vi.fn();
    render(
      <GenerationProgress
        currentStage="DISH_ANALYSIS"
        succeededStages={[]}
        totalStages={9}
        onCancel={onCancel}
      />,
    );
    expect(screen.getByRole("button", { name: copy.cancelGeneration })).toBeVisible();
  });
});
