import "@testing-library/jest-dom/vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { useState } from "react";
import { describe, expect, it } from "vitest";
import { catalogs } from "../../i18n/copy";
import { PixelModal } from "./PixelModal";

function Harness() {
  const [open, setOpen] = useState(false);
  return (
    <>
      <button type="button" onClick={() => setOpen(true)}>
        open
      </button>
      {open && (
        <PixelModal title="选择分类" onClose={() => setOpen(false)}>
          <button type="button">第一项</button>
        </PixelModal>
      )}
    </>
  );
}

describe("PixelModal", () => {
  it("closes on Escape and restores focus to the opener", () => {
    render(<Harness />);
    const opener = screen.getByRole("button", { name: "open" });
    opener.focus();
    fireEvent.click(opener);

    expect(screen.getByRole("dialog", { name: "选择分类" })).toBeInTheDocument();
    fireEvent.keyDown(document, { key: "Escape" });

    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(document.activeElement).toBe(opener);
  });

  it("keeps the close action labelled for screen readers", () => {
    render(<Harness />);
    fireEvent.click(screen.getByRole("button", { name: "open" }));
    expect(
      screen.getByRole("button", { name: catalogs["zh-CN"].pickClose }),
    ).toBeInTheDocument();
  });
});
