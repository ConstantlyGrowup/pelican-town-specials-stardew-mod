import "@testing-library/jest-dom/vitest";
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { GameObjectIcon, GameUiIcon, SpecificIcon } from "./GameAssetIcon";

describe("GameAssetIcon", () => {
  it("maps an object id to a 16px springobjects tile", () => {
    render(<GameObjectIcon itemId="24" alt="防风草图标" size={32} />);

    const icon = screen.getByRole("img", { name: "防风草图标" });
    expect(icon).toHaveStyle({
      backgroundImage: 'url("/assets/game/springobjects.png")',
      backgroundPosition: "0px -32px",
      backgroundSize: "768px 1248px",
    });
  });

  it("renders a fixed UI sprite from the localized Cursors atlas", () => {
    render(<GameUiIcon name="health" alt="生命图标" size={24} />);

    expect(screen.getByRole("img", { name: "生命图标" })).toHaveStyle({
      backgroundImage: 'url("/assets/game/Cursors.zh-CN.png")',
      backgroundPosition: "-24px -624px",
    });
  });

  it("uses the vanilla collection, gift and gold UI sprites", () => {
    render(
      <>
        <GameUiIcon name="collections" alt="收集品图标" size={32} />
        <GameUiIcon name="gift" alt="礼物图标" size={32} />
        <GameUiIcon name="gold" alt="金币图标" size={32} />
      </>,
    );

    expect(screen.getByRole("img", { name: "收集品图标" })).toHaveStyle({
      backgroundPosition: "-160px -736px",
    });
    expect(screen.getByRole("img", { name: "礼物图标" })).toHaveStyle({
      backgroundPosition: "-96px 0px",
    });
    expect(screen.getByRole("img", { name: "金币图标" })).toHaveStyle({
      backgroundPosition: "-832px -928px",
    });
  });

  it("renders the user-supplied extracted semantic icons", () => {
    render(
      <>
        <SpecificIcon name="edibility" alt="饱腹度图标" size={32} />
        <SpecificIcon name="health" alt="生命恢复图标" size={32} />
        <SpecificIcon name="sellPrice" alt="售价图标" size={32} />
        <SpecificIcon name="createFirstDish" alt="创建第一道菜图标" size={32} />
        <SpecificIcon name="blueprint" alt="料理蓝图图标" size={32} />
      </>,
    );

    for (const name of [
      "饱腹度图标",
      "生命恢复图标",
      "售价图标",
      "创建第一道菜图标",
      "料理蓝图图标",
    ]) {
      expect(screen.getByRole("img", { name })).toHaveClass("specific-icon");
      expect(screen.getByRole("img", { name })).toHaveAttribute(
        "src",
        expect.stringContaining("/assets/game/specific-icons/"),
      );
    }
  });
});
