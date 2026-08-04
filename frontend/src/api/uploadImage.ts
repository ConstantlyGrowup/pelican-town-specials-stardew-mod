import { apiClient } from "./client";
import type { components } from "./generated/schema";

type AssetView = components["schemas"]["AssetView"];

/**
 * Narrow multipart transport adapter. The generated schema types the binary
 * upload body as a string, but browsers must send FormData; the adapter keeps
 * that serialization detail local while still using the generated path.
 */
export async function uploadImage(file: File): Promise<AssetView> {
  const form = new FormData();
  form.append("file", file);
  const { data, error } = await apiClient.POST("/api/v1/assets/images", {
    body: form as never,
  });
  if (error || !data) {
    throw new Error("upload failed");
  }
  return data;
}
