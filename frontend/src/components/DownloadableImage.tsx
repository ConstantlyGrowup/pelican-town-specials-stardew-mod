import type { CSSProperties } from "react";
import { PRODUCT_COPY } from "../i18n/copy";

const IMAGE_EXTENSION_BY_TYPE: Record<string, string> = {
  "image/png": "png",
  "image/jpeg": "jpg",
  "image/webp": "webp",
};

function sanitizeFileNameBase(value: string): string {
  const cleaned = value
    .trim()
    .replace(/[\\/:*?"<>|]/g, "_")
    .split("")
    .map((ch) => ((ch.codePointAt(0) ?? 0) < 32 ? "_" : ch))
    .join("");
  return cleaned || "dish";
}

type DownloadableImageProps = {
  src: string;
  alt: string;
  /** Base file name without extension; the detected image extension is appended. */
  downloadName: string;
  width?: number;
  height?: number;
  style?: CSSProperties;
};

/**
 * Renders an image preview with a small download entry that appears on hover
 * (and on keyboard focus). Clicking downloads the raw image bytes with a
 * MIME-matched file name instead of relying on right-click "save image as".
 * The extension is detected from the response so JPEG/WebP previews download
 * with the correct suffix regardless of what the model returned.
 */
export function DownloadableImage({
  src,
  alt,
  downloadName,
  ...imgProps
}: DownloadableImageProps) {
  const copy = PRODUCT_COPY.zh;

  async function onDownload() {
    let response: Response;
    try {
      response = await fetch(src, { credentials: "same-origin" });
    } catch {
      return;
    }
    if (!response.ok) {
      return;
    }
    let blob: Blob;
    try {
      blob = await response.blob();
    } catch {
      return;
    }
    const extension = IMAGE_EXTENSION_BY_TYPE[blob.type] ?? "png";
    const objectUrl = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = objectUrl;
    anchor.download = `${sanitizeFileNameBase(downloadName)}.${extension}`;
    document.body.appendChild(anchor);
    anchor.click();
    anchor.remove();
    // Revoking immediately can abort an in-flight download in some browsers.
    window.setTimeout(() => URL.revokeObjectURL(objectUrl), 1000);
  }

  return (
    <span className="downloadable-image">
      <img src={src} alt={alt} {...imgProps} />
      <button
        type="button"
        className="downloadable-image__button"
        onClick={() => void onDownload()}
        aria-label={copy.downloadImage}
        title={copy.downloadImage}
      >
        <svg
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
          aria-hidden="true"
          focusable="false"
        >
          <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
          <polyline points="7 10 12 15 17 10" />
          <line x1="12" y1="15" x2="12" y2="3" />
        </svg>
      </button>
    </span>
  );
}
