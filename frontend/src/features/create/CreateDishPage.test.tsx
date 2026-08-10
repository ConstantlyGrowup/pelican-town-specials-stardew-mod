import "@testing-library/jest-dom/vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { setupServer } from "msw/node";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterAll, afterEach, beforeAll, describe, expect, it, vi } from "vitest";
import { catalogs, LOCALE_STORAGE_KEY } from "../../i18n/copy";
import { LocaleProvider } from "../../i18n/locale";
import { CreateDishPage } from "./CreateDishPage";

const copy = catalogs["zh-CN"];

const server = setupServer();

beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
afterEach(() => {
  server.resetHandlers();
  window.localStorage.clear();
});
afterAll(() => server.close());

const assetView = {
  assetId: "asset-1",
  kind: "ORIGINAL_IMAGE",
  mediaType: "image/png",
  sha256: "a".repeat(64),
  byteSize: 10,
  createdAt: "2026-08-04T00:00:00Z",
  width: 8,
  height: 8,
};

const draftView = {
  draftId: "draft-1",
  mode: "BLUEPRINT",
  baseTemplateVersion: "blueprint-v1",
  status: "DRAFT",
  revision: 1,
  source: { originalImageAssetId: "asset-1", contextText: null, language: "zh-CN" },
  analysis: null,
  presentation: null,
  gameplay: null,
  visuals: null,
  provenance: {
    mode: "BLUEPRINT",
    authorityByField: {},
    visionModel: null,
    textModel: null,
    imageModel: null,
    promptVersions: {},
    generationSource: "USER_AUTHORED",
    canonicalDishSignature: null,
    cacheEligibility: false,
  },
  lastError: null,
  createdAt: "2026-08-04T00:00:00Z",
  updatedAt: "2026-08-04T00:00:00Z",
  archivedDishId: null,
};

function renderPage() {
  return render(
    <MemoryRouter initialEntries={["/create"]}>
      <Routes>
        <Route path="/create" element={<CreateDishPage />} />
        <Route path="/drafts/:draftId" element={<div>draft page</div>} />
      </Routes>
    </MemoryRouter>,
  );
}

function renderPageWithLocale() {
  return render(
    <LocaleProvider>
      <MemoryRouter initialEntries={["/create"]}>
        <Routes>
          <Route path="/create" element={<CreateDishPage />} />
          <Route path="/drafts/:draftId" element={<div>draft page</div>} />
        </Routes>
      </MemoryRouter>
    </LocaleProvider>,
  );
}

describe("create dish page", () => {
  it("explains that Blueprint starts from the original image only", () => {
    const { container } = renderPage();

    expect(container.querySelector('img[src="/assets/ui/gus-portrait-2.png"]')).not.toBeNull();

    fireEvent.click(screen.getByRole("button", { name: copy.createBlueprint }));

    expect(screen.getByText(copy.blueprintFromOriginalOnly)).toBeVisible();
    expect(container.querySelector(".specific-icon--blueprint")).not.toBeNull();
  });

  it("uploads the image first, then creates the draft with only the assetId", async () => {
    const createSpy = vi.fn((info: { request: Request }) => {
      void info;
      return HttpResponse.json(draftView);
    });
    server.use(
      http.post("/api/v1/assets/images", () => HttpResponse.json(assetView)),
      http.post("/api/v1/drafts", createSpy),
    );
    renderPage();

    const file = new File(["x"], "photo.png", { type: "image/png" });
    fireEvent.change(screen.getByLabelText(copy.uploadLabel), {
      target: { files: [file] },
    });
    const createButton = await screen.findByRole("button", {
      name: copy.createDraft,
    });
    await waitFor(() => expect(createButton).toBeEnabled());
    fireEvent.click(createButton);

    expect(await screen.findByText("draft page")).toBeVisible();
    const request = createSpy.mock.calls[0]?.[0]?.request as Request;
    const body = (await request.clone().json()) as {
      mode: string;
      language: string;
      source: { originalImageAssetId: string };
    };
    expect(body.mode).toBe("ASK_GUS");
    expect(body.language).toBe("zh-CN");
    expect(body.source.originalImageAssetId).toBe("asset-1");
  });

  it("sends the current UI locale as the draft language", async () => {
    window.localStorage.setItem(LOCALE_STORAGE_KEY, "en-US");
    const en = catalogs["en-US"];
    const createSpy = vi.fn((info: { request: Request }) => {
      void info;
      return HttpResponse.json(draftView);
    });
    server.use(
      http.post("/api/v1/assets/images", () => HttpResponse.json(assetView)),
      http.post("/api/v1/drafts", createSpy),
    );
    renderPageWithLocale();

    const file = new File(["x"], "photo.png", { type: "image/png" });
    fireEvent.change(screen.getByLabelText(en.uploadLabel), {
      target: { files: [file] },
    });
    const createButton = await screen.findByRole("button", {
      name: en.createDraft,
    });
    await waitFor(() => expect(createButton).toBeEnabled());
    fireEvent.click(createButton);

    await screen.findByText("draft page");
    const request = createSpy.mock.calls[0]?.[0]?.request as Request;
    const body = (await request.clone().json()) as { language: string };
    expect(body.language).toBe("en-US");
  });
});
