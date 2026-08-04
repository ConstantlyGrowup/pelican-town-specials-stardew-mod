import { z } from "zod";
import type { components } from "../../api/generated/schema";

type ProviderSettingsView = components["schemas"]["ProviderSettingsView"];
type ProviderSettingsUpdate = components["schemas"]["ProviderSettingsUpdate"];

export const providerSettingsSchema = z.object({
  baseUrl: z
    .string()
    .url("请输入有效的 URL。")
    .refine((value) => value.startsWith("http://") || value.startsWith("https://"), {
      message: "Base URL 必须是 http 或 https。",
    }),
  visionModel: z.string().trim().min(1, "必填").max(120),
  textModel: z.string().trim().min(1, "必填").max(120),
  imageModel: z.string().trim().min(1, "必填").max(120),
  chatTimeoutSeconds: z.coerce.number().int().min(30, "30–600").max(600),
  imageTimeoutSeconds: z.coerce.number().int().min(60, "60–900").max(900),
  maxAutomaticRetries: z.coerce.number().int().min(0).max(3),
});

export type ProviderSettingsValues = z.infer<typeof providerSettingsSchema>;

export function fromView(view: ProviderSettingsView): ProviderSettingsValues {
  return {
    baseUrl: view.baseUrl,
    visionModel: view.visionModel,
    textModel: view.textModel,
    imageModel: view.imageModel,
    chatTimeoutSeconds: view.chatTimeoutSeconds,
    imageTimeoutSeconds: view.imageTimeoutSeconds,
    maxAutomaticRetries: view.maxAutomaticRetries,
  };
}

export function toUpdate(values: ProviderSettingsValues): ProviderSettingsUpdate {
  return {
    providerKind: "OPENAI_COMPATIBLE",
    baseUrl: values.baseUrl,
    visionModel: values.visionModel,
    textModel: values.textModel,
    imageModel: values.imageModel,
    chatTimeoutSeconds: values.chatTimeoutSeconds,
    imageTimeoutSeconds: values.imageTimeoutSeconds,
    maxAutomaticRetries: values.maxAutomaticRetries,
  };
}
