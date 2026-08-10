import "@testing-library/jest-dom/vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { setupServer } from "msw/node";
import { afterAll, afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import { catalogs } from "../../i18n/copy";
import { LocaleProvider } from "../../i18n/locale";
import { SettingsPage } from "./SettingsPage";

const copy = catalogs["zh-CN"];

const settingsView = {
  providerKind: "OPENAI_COMPATIBLE",
  baseUrl: "https://yibuapi.com/v1",
  visionModel: "vision-model",
  textModel: "text-model",
  imageModel: "image-model",
  chatTimeoutSeconds: 120,
  imageTimeoutSeconds: 300,
  maxAutomaticRetries: 2,
  apiKeyConfigured: false,
  apiKeySource: "NONE",
};

const keyStatus = {
  apiKeyConfigured: true,
  apiKeySource: "ENVIRONMENT",
};

const server = setupServer();

beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
afterEach(() => {
  server.resetHandlers();
  window.localStorage.clear();
  document.documentElement.lang = "";
});
afterAll(() => server.close());

function renderPage() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <SettingsPage />
    </QueryClientProvider>,
  );
}

function renderPageWithLocale() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <LocaleProvider>
        <SettingsPage />
      </LocaleProvider>
    </QueryClientProvider>,
  );
}

describe("settings page", () => {
  beforeEach(() => {
    server.use(
      http.get("/api/v1/settings/provider", () => HttpResponse.json(settingsView)),
    );
  });

  it("loads and displays non-secret provider settings without echoing the key", async () => {
    renderPage();

    await screen.findByDisplayValue("https://yibuapi.com/v1");
    expect(screen.getByText(/未配置/)).toBeVisible();
    expect(screen.queryByText("sk-")).not.toBeInTheDocument();
  });

  it("validates the form and rejects an invalid base URL without PUT", async () => {
    const putSpy = vi.fn(() => HttpResponse.json(settingsView));
    server.use(http.put("/api/v1/settings/provider", putSpy));
    renderPage();

    await screen.findByDisplayValue("https://yibuapi.com/v1");
    const urlInput = screen.getByLabelText(copy.baseUrlLabel);
    fireEvent.change(urlInput, { target: { value: "not-a-url" } });
    fireEvent.click(screen.getByRole("button", { name: copy.saveSettings }));

    expect(putSpy).not.toHaveBeenCalled();
    expect(await screen.findByRole("alert")).toBeVisible();
  });

  it("saves settings via PUT and shows a success message", async () => {
    server.use(
      http.put("/api/v1/settings/provider", () => HttpResponse.json(settingsView)),
    );
    renderPage();

    await screen.findByDisplayValue("https://yibuapi.com/v1");
    fireEvent.click(screen.getByRole("button", { name: copy.saveSettings }));

    expect(await screen.findByText(copy.settingsSaved)).toBeVisible();
  });

  it("saves the API key and clears the password input value immediately", async () => {
    server.use(
      http.put("/api/v1/settings/provider/key", () => HttpResponse.json(keyStatus)),
    );
    renderPage();

    await screen.findByDisplayValue("https://yibuapi.com/v1");
    const keyInput = screen.getByPlaceholderText(
      copy.apiKeyPlaceholder,
    ) as HTMLInputElement;
    fireEvent.change(keyInput, { target: { value: "sk-sentinel-value" } });

    fireEvent.click(screen.getByRole("button", { name: copy.saveApiKey }));

    expect(await screen.findByText(copy.settingsSaved)).toBeVisible();
    await waitFor(() => expect(keyInput.value).toBe(""));
    expect(screen.getByText(/已配置/)).toBeVisible();
  });

  it("deletes the API key and reflects the new status", async () => {
    server.use(
      http.delete("/api/v1/settings/provider/key", () =>
        HttpResponse.json({ ...keyStatus, apiKeyConfigured: false }),
      ),
    );
    renderPage();

    await screen.findByDisplayValue("https://yibuapi.com/v1");
    fireEvent.click(screen.getByRole("button", { name: copy.deleteApiKey }));

    expect(await screen.findByText(/未配置/)).toBeVisible();
  });
});

describe("settings language toggle", () => {
  beforeEach(() => {
    server.use(
      http.get("/api/v1/settings/provider", () => HttpResponse.json(settingsView)),
    );
  });

  it("renders the language radiogroup with selected state and aria labels", async () => {
    renderPageWithLocale();
    await screen.findByDisplayValue("https://yibuapi.com/v1");

    const group = screen.getByRole("radiogroup", { name: copy.languageSectionTitle });
    const chinese = screen.getByRole("radio", { name: copy.languageChineseLabel });
    const english = screen.getByRole("radio", { name: copy.languageEnglishLabel });
    expect(group).toBeInTheDocument();
    expect(chinese).toHaveAttribute("aria-checked", "true");
    expect(english).toHaveAttribute("aria-checked", "false");
  });

  it("switches the current page copy immediately when English is chosen", async () => {
    renderPageWithLocale();
    await screen.findByDisplayValue("https://yibuapi.com/v1");

    fireEvent.click(screen.getByRole("radio", { name: copy.languageEnglishLabel }));

    const en = catalogs["en-US"];
    expect(screen.getByText(en.settingsSubtitle)).toBeVisible();
    expect(screen.getByRole("radio", { name: en.languageEnglishLabel })).toHaveAttribute(
      "aria-checked",
      "true",
    );
    expect(document.documentElement.lang).toBe("en-US");
    expect(window.localStorage.getItem("pts-locale")).toBe("en-US");
  });

  it("moves the selection with arrow keys and keeps it within the group", async () => {
    renderPageWithLocale();
    await screen.findByDisplayValue("https://yibuapi.com/v1");

    const group = screen.getByRole("radiogroup", { name: copy.languageSectionTitle });
    fireEvent.keyDown(group, { key: "ArrowRight" });

    const en = catalogs["en-US"];
    expect(screen.getByRole("radio", { name: en.languageEnglishLabel })).toHaveAttribute(
      "aria-checked",
      "true",
    );
    // ArrowRight past the last option wraps back to the first.
    fireEvent.keyDown(group, { key: "ArrowRight" });
    expect(screen.getByRole("radio", { name: copy.languageChineseLabel })).toHaveAttribute(
      "aria-checked",
      "true",
    );
  });

  it("moves focus to the newly selected radio on arrow-key navigation (roving tabIndex)", async () => {
    renderPageWithLocale();
    await screen.findByDisplayValue("https://yibuapi.com/v1");

    const group = screen.getByRole("radiogroup", { name: copy.languageSectionTitle });
    const chinese = screen.getByRole("radio", { name: copy.languageChineseLabel });
    const english = screen.getByRole("radio", { name: copy.languageEnglishLabel });
    // Only the selected radio is reachable by tab; the rest are skipped.
    expect(chinese).toHaveAttribute("tabindex", "0");
    expect(english).toHaveAttribute("tabindex", "-1");

    fireEvent.keyDown(group, { key: "ArrowRight" });

    expect(english).toHaveAttribute("aria-checked", "true");
    expect(english).toHaveAttribute("tabindex", "0");
    expect(chinese).toHaveAttribute("tabindex", "-1");
    expect(document.activeElement).toBe(english);
  });
});
