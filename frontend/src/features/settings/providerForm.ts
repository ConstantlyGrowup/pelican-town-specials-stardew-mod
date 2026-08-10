import { z } from "zod";
import type { components } from "../../api/generated/schema";
import type { Copy } from "../../i18n/copy";

type ProviderSettingsView = components["schemas"]["ProviderSettingsView"];
type ProviderSettingsUpdate = components["schemas"]["ProviderSettingsUpdate"];

/**
 * Provider settings schema with locale-aware validation messages. The catalog
 * is injected so the same zod rules can report errors in the active UI locale.
 */
export function createProviderFormSchema(copy: Copy) {
  return z.object({
    baseUrl: z
      .string()
      .url(copy.providerUrlInvalid)
      .refine((value) => value.startsWith("http://") || value.startsWith("https://"), {
        message: copy.providerUrlScheme,
      }),
    visionModel: z.string().trim().min(1, copy.providerRequired).max(120),
    textModel: z.string().trim().min(1, copy.providerRequired).max(120),
    imageModel: z.string().trim().min(1, copy.providerRequired).max(120),
    chatTimeoutSeconds: z.coerce.number().int().min(30, copy.providerChatTimeoutRange).max(600),
    imageTimeoutSeconds: z.coerce.number().int().min(60, copy.providerImageTimeoutRange).max(900),
    maxAutomaticRetries: z.coerce.number().int().min(0).max(3),
  });
}

export type ProviderSettingsValues = z.infer<ReturnType<typeof createProviderFormSchema>>;

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
