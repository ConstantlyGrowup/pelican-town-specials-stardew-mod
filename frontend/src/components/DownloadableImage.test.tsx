import "@testing-library/jest-dom/vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { catalogs } from "../i18n/copy";
import { DownloadableImage } from "./DownloadableImage";

const copy = catalogs["zh-CN"];

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("DownloadableImage", () => {
  it("renders the preview image with a hover download entry", () => {
    render(
      <DownloadableImage
        src="/api/v1/assets/preview-1"
        alt="南瓜汤预览"
        downloadName="南瓜汤-预览"
      />,
    );

    expect(screen.getByRole("img", { name: "南瓜汤预览" })).toHaveAttribute(
      "src",
      "/api/v1/assets/preview-1",
    );
    expect(screen.getByRole("button", { name: copy.downloadImage })).toBeInTheDocument();
  });

  it("downloads the image bytes with a MIME-matched file name on click", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      blob: () => Promise.resolve(new Blob(["fake-image"], { type: "image/png" })),
    });
    vi.stubGlobal("fetch", fetchMock);
    const createObjectURL = vi.fn(() => "blob:mock-url");
    const revokeObjectURL = vi.fn();
    vi.stubGlobal("URL", { createObjectURL, revokeObjectURL } as unknown as typeof URL);
    const anchorClick = vi
      .spyOn(HTMLAnchorElement.prototype, "click")
      .mockImplementation(() => undefined);

    render(
      <DownloadableImage
        src="/api/v1/assets/preview-1"
        alt="南瓜汤预览"
        downloadName="南瓜汤-预览"
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: copy.downloadImage }));

    await waitFor(() => expect(anchorClick).toHaveBeenCalled());
    expect(fetchMock).toHaveBeenCalledWith("/api/v1/assets/preview-1", {
      credentials: "same-origin",
    });
    const anchor = anchorClick.mock.contexts[0] as HTMLAnchorElement;
    expect(anchor.download).toBe("南瓜汤-预览.png");
    expect(anchor.href).toBe("blob:mock-url");
    expect(createObjectURL).toHaveBeenCalledTimes(1);
    await waitFor(
      () => expect(revokeObjectURL).toHaveBeenCalledWith("blob:mock-url"),
      { timeout: 3000 },
    );
  });
});
