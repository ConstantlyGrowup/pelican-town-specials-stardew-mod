import "@testing-library/jest-dom/vitest";
import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it } from "vitest";
import { catalogs, LOCALE_STORAGE_KEY } from "../../i18n/copy";
import { LocaleProvider } from "../../i18n/locale";
import { TrialUsageBadge } from "./TrialUsageBadge";

beforeEach(() => {
  window.localStorage.clear();
});

function renderBadge(
  fact: { remaining: number } | null | undefined,
  locale: "zh-CN" | "en-US" = "zh-CN",
) {
  window.localStorage.setItem(LOCALE_STORAGE_KEY, locale);
  return render(
    <LocaleProvider>
      <TrialUsageBadge fact={fact} />
    </LocaleProvider>,
  );
}

describe("TrialUsageBadge", () => {
  it("renders the confirmed remaining trial fact in Chinese as a non-interactive status", () => {
    renderBadge({ remaining: 1 });

    const expected = catalogs["zh-CN"].trialUsageBadge.replace("{remaining}", "1");
    const status = screen.getByRole("status", { name: expected });
    expect(status).toHaveTextContent(expected);
    expect(status).not.toHaveAttribute("tabindex");
    expect(screen.queryByRole("button")).toBeNull();
  });

  it("renders the same fact with English visible and screen-reader copy", () => {
    renderBadge({ remaining: 0 }, "en-US");

    const expected = catalogs["en-US"].trialUsageBadge.replace("{remaining}", "0");
    expect(screen.getByRole("status", { name: expected })).toHaveTextContent(expected);
  });

  it.each([
    { fact: null, label: "missing fact" },
    { fact: undefined, label: "undefined fact" },
    { fact: { remaining: -1 }, label: "negative remaining" },
    { fact: { remaining: 1.5 }, label: "fractional remaining" },
    { fact: { remaining: Number.NaN }, label: "NaN remaining" },
    { fact: { remaining: Number.POSITIVE_INFINITY }, label: "infinite remaining" },
  ])("renders nothing for $label", ({ fact }) => {
    const { container } = renderBadge(fact);
    expect(container).toBeEmptyDOMElement();
  });
});
