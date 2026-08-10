import "@testing-library/jest-dom/vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it } from "vitest";
import { catalogs, DEFAULT_LOCALE, LOCALE_STORAGE_KEY } from "./copy";
import { LocaleProvider, useCopy, useLocale, useSetLocale } from "./locale";

function Probe() {
  const locale = useLocale();
  const copy = useCopy();
  const setLocale = useSetLocale();
  return (
    <div>
      <span data-testid="locale">{locale}</span>
      <span data-testid="product">{copy.productName}</span>
      <button type="button" onClick={() => setLocale("en-US")}>
        switch-en
      </button>
      <button type="button" onClick={() => setLocale("zh-CN")}>
        switch-zh
      </button>
    </div>
  );
}

function renderProbe() {
  return render(
    <LocaleProvider>
      <Probe />
    </LocaleProvider>,
  );
}

beforeEach(() => {
  window.localStorage.clear();
  document.documentElement.lang = "";
});

describe("LocaleProvider", () => {
  it("defaults to zh-CN when nothing is stored", () => {
    renderProbe();
    expect(screen.getByTestId("locale")).toHaveTextContent(DEFAULT_LOCALE);
    expect(screen.getByTestId("product")).toHaveTextContent(
      catalogs["zh-CN"].productName,
    );
  });

  it("falls back to zh-CN for an invalid stored value", () => {
    window.localStorage.setItem(LOCALE_STORAGE_KEY, "fr-FR");
    renderProbe();
    expect(screen.getByTestId("locale")).toHaveTextContent("zh-CN");
  });

  it("falls back to zh-CN when the stored value is cleared", () => {
    window.localStorage.setItem(LOCALE_STORAGE_KEY, "en-US");
    window.localStorage.removeItem(LOCALE_STORAGE_KEY);
    renderProbe();
    expect(screen.getByTestId("locale")).toHaveTextContent("zh-CN");
  });

  it("restores a persisted locale on mount", () => {
    window.localStorage.setItem(LOCALE_STORAGE_KEY, "en-US");
    renderProbe();
    expect(screen.getByTestId("locale")).toHaveTextContent("en-US");
    expect(screen.getByTestId("product")).toHaveTextContent(
      catalogs["en-US"].productName,
    );
  });

  it("persists the selection and updates copy immediately", () => {
    renderProbe();
    fireEvent.click(screen.getByText("switch-en"));
    expect(screen.getByTestId("locale")).toHaveTextContent("en-US");
    expect(screen.getByTestId("product")).toHaveTextContent(
      catalogs["en-US"].productName,
    );
    expect(window.localStorage.getItem(LOCALE_STORAGE_KEY)).toBe("en-US");
  });

  it("keeps document.documentElement.lang in sync", () => {
    window.localStorage.setItem(LOCALE_STORAGE_KEY, "en-US");
    renderProbe();
    expect(document.documentElement.lang).toBe("en-US");
    fireEvent.click(screen.getByText("switch-zh"));
    expect(document.documentElement.lang).toBe("zh-CN");
  });
});
