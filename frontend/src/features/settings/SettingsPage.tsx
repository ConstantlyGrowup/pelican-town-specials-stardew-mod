import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useRef, useState } from "react";
import { useForm, useFormState } from "react-hook-form";
import { apiClient } from "../../api/client";
import type { components } from "../../api/generated/schema";
import { PRODUCT_COPY } from "../../i18n/copy";
import {
  fromView,
  providerSettingsSchema,
  toUpdate,
  type ProviderSettingsValues,
} from "./providerForm";

type ProviderKeyStatus = components["schemas"]["ProviderKeyStatus"];

export function SettingsPage() {
  const copy = PRODUCT_COPY.zh;
  const queryClient = useQueryClient();
  const [saveMessage, setSaveMessage] = useState<string | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const keyInputRef = useRef<HTMLInputElement>(null);
  const [keyStatus, setKeyStatus] = useState<ProviderKeyStatus | null>(null);
  const [keyMessage, setKeyMessage] = useState<string | null>(null);

  const form = useForm<ProviderSettingsValues>({
    defaultValues: {
      baseUrl: "",
      visionModel: "",
      textModel: "",
      imageModel: "",
      chatTimeoutSeconds: 120,
      imageTimeoutSeconds: 300,
      maxAutomaticRetries: 2,
    },
  });
  const { register, handleSubmit, reset, setError, clearErrors } = form;
  const formState = useFormState({ control: form.control });

  useQuery({
    queryKey: ["provider-settings"],
    queryFn: async () => {
      const { data, error } = await apiClient.GET("/api/v1/settings/provider");
      if (error || !data) {
        setLoadError(copy.settingsLoadFailed);
        throw new Error("load failed");
      }
      setLoadError(null);
      reset(fromView(data));
      setKeyStatus({
        apiKeyConfigured: data.apiKeyConfigured,
        apiKeySource: data.apiKeySource,
      });
      return data;
    },
  });

  async function onSave(values: ProviderSettingsValues) {
    const parsed = providerSettingsSchema.safeParse(values);
    if (!parsed.success) {
      for (const issue of parsed.error.issues) {
        const field = issue.path[0] as keyof ProviderSettingsValues | undefined;
        if (field) {
          setError(field, { type: "manual", message: issue.message });
        }
      }
      return;
    }
    clearErrors();
    const { error } = await apiClient.PUT("/api/v1/settings/provider", {
      body: toUpdate(parsed.data),
    });
    if (error) {
      setSaveMessage(copy.saveFailed);
      return;
    }
    setSaveMessage(copy.settingsSaved);
    await queryClient.invalidateQueries({ queryKey: ["provider-settings"] });
  }

  async function onSaveKey() {
    const keyValue = keyInputRef.current?.value ?? "";
    if (!keyValue) {
      return;
    }
    const { data, error } = await apiClient.PUT("/api/v1/settings/provider/key", {
      body: { apiKey: keyValue },
    });
    if (error || !data) {
      setKeyMessage(copy.saveFailed);
      return;
    }
    setKeyStatus(data);
    if (keyInputRef.current) {
      keyInputRef.current.value = "";
    }
    setKeyMessage(copy.settingsSaved);
  }

  async function onDeleteKey() {
    const { data, error } = await apiClient.DELETE("/api/v1/settings/provider/key");
    if (error || !data) {
      setKeyMessage(copy.deleteFailed);
      return;
    }
    setKeyStatus(data);
    setKeyMessage(copy.settingsSaved);
  }

  return (
    <main className="settings-page">
      <div className="page-header">
        <div>
          <p className="eyebrow">SETTINGS / PROVIDER CONNECTION</p>
          <h1>{copy.settingsTitle}</h1>
          <p className="page-subtitle">连接你的视觉、文本和图像 Provider。</p>
        </div>
        <span className="settings-mark" aria-hidden="true">⚙</span>
      </div>
      {loadError && <div className="status-banner status-error">{loadError}</div>}

      <form onSubmit={handleSubmit(onSave)} className="paper-panel settings-form">
        <div className="panel-section-heading">
          <div>
            <p className="eyebrow">01 / MODEL ROUTING</p>
            <h2>Provider 参数</h2>
          </div>
          <span className="field-counter">LOCAL ONLY</span>
        </div>
        <div className="field">
          <label htmlFor="baseUrl">{copy.baseUrlLabel}</label>
          <input id="baseUrl" {...register("baseUrl")} />
          {formState.errors.baseUrl && (
            <span className="error" role="alert">
              {formState.errors.baseUrl.message}
            </span>
          )}
        </div>
        <div className="field">
          <label htmlFor="visionModel">{copy.visionModelLabel}</label>
          <input id="visionModel" {...register("visionModel")} />
          {formState.errors.visionModel && (
            <span className="error" role="alert">
              {formState.errors.visionModel.message}
            </span>
          )}
        </div>
        <div className="field">
          <label htmlFor="textModel">{copy.textModelLabel}</label>
          <input id="textModel" {...register("textModel")} />
          {formState.errors.textModel && (
            <span className="error" role="alert">
              {formState.errors.textModel.message}
            </span>
          )}
        </div>
        <div className="field">
          <label htmlFor="imageModel">{copy.imageModelLabel}</label>
          <input id="imageModel" {...register("imageModel")} />
          {formState.errors.imageModel && (
            <span className="error" role="alert">
              {formState.errors.imageModel.message}
            </span>
          )}
        </div>
        <div className="field">
          <label htmlFor="chatTimeoutSeconds">{copy.chatTimeoutLabel}</label>
          <input
            id="chatTimeoutSeconds"
            type="number"
            {...register("chatTimeoutSeconds", { valueAsNumber: true })}
          />
          {formState.errors.chatTimeoutSeconds && (
            <span className="error" role="alert">
              {formState.errors.chatTimeoutSeconds.message}
            </span>
          )}
        </div>
        <div className="field">
          <label htmlFor="imageTimeoutSeconds">{copy.imageTimeoutLabel}</label>
          <input
            id="imageTimeoutSeconds"
            type="number"
            {...register("imageTimeoutSeconds", { valueAsNumber: true })}
          />
          {formState.errors.imageTimeoutSeconds && (
            <span className="error" role="alert">
              {formState.errors.imageTimeoutSeconds.message}
            </span>
          )}
        </div>
        <div className="field">
          <label htmlFor="maxAutomaticRetries">{copy.maxRetriesLabel}</label>
          <input
            id="maxAutomaticRetries"
            type="number"
            {...register("maxAutomaticRetries", { valueAsNumber: true })}
          />
          {formState.errors.maxAutomaticRetries && (
            <span className="error" role="alert">
              {formState.errors.maxAutomaticRetries.message}
            </span>
          )}
        </div>
        {saveMessage && <p role="status">{saveMessage}</p>}
        <button className="btn btn-primary" type="submit" disabled={formState.isSubmitting}>
          {copy.saveSettings}
        </button>
      </form>

      <section className="paper-panel settings-key-panel" aria-label={copy.apiKeyStatusLabel}>
        <div className="panel-section-heading">
          <div>
            <p className="eyebrow">02 / SECRET</p>
            <h2>{copy.apiKeyStatusLabel}</h2>
          </div>
          <span className="settings-key-status">
            {keyStatus?.apiKeyConfigured ? copy.apiKeyConfigured : copy.apiKeyNotConfigured}
          </span>
        </div>
        <div className="field">
          <label htmlFor="apiKey">{copy.apiKeyStatusLabel}</label>
          <input
            id="apiKey"
            type="password"
            ref={keyInputRef}
            placeholder={copy.apiKeyPlaceholder}
          />
        </div>
        {keyMessage && <p role="status">{keyMessage}</p>}
        <button className="btn btn-primary" type="button" onClick={onSaveKey}>
          {copy.saveApiKey}
        </button>
        <button className="btn btn-danger" type="button" onClick={onDeleteKey}>
          {copy.deleteApiKey}
        </button>
      </section>
    </main>
  );
}
