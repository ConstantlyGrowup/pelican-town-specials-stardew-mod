import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useRef, useState, type KeyboardEvent } from "react";
import { useForm, useFormState } from "react-hook-form";
import { apiClient } from "../../api/client";
import type { components } from "../../api/generated/schema";
import { useCopy, useLocale, useSetLocale } from "../../i18n/locale";
import type { Language } from "../../i18n/copy";
import {
  createProviderFormSchema,
  fromView,
  toUpdate,
  type ProviderSettingsValues,
} from "./providerForm";

type ProviderKeyStatus = components["schemas"]["ProviderKeyStatus"];
type TrialStatus = components["schemas"]["TrialStatus"];

// Transient status/error messages store a catalog key so a live message
// re-localizes when the user switches the UI language (M7-T25-I18N-001).
type SettingsMessageKey =
  | "settingsLoadFailed"
  | "settingsSaved"
  | "saveFailed"
  | "deleteFailed"
  | "trialEnableFailed"
  | "trialExitFailed";

export function SettingsPage() {
  const copy = useCopy();
  const locale = useLocale();
  const setLocale = useSetLocale();
  const queryClient = useQueryClient();
  const radioRefs = useRef<(HTMLButtonElement | null)[]>([]);
  // Language names are shown in their own language regardless of the active
  // locale, so they come from the catalog like every other user-visible label.
  const localeOptions: Array<{ value: Language; label: string }> = [
    { value: "zh-CN", label: copy.languageChinese },
    { value: "en-US", label: copy.languageEnglish },
  ];
  const [saveMessage, setSaveMessage] = useState<SettingsMessageKey | null>(null);
  const [loadError, setLoadError] = useState<SettingsMessageKey | null>(null);
  const keyInputRef = useRef<HTMLInputElement>(null);
  const [keyStatus, setKeyStatus] = useState<ProviderKeyStatus | null>(null);
  const [keyMessage, setKeyMessage] = useState<SettingsMessageKey | null>(null);
  // `null` means "still loading or the trial status endpoint failed"; the
  // panel simply stays quiet so a transient network failure never crashes the
  // Settings page or masks the personal provider form.
  const [trialStatus, setTrialStatus] = useState<TrialStatus | null>(null);
  const [trialMessage, setTrialMessage] = useState<SettingsMessageKey | null>(null);

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
        setLoadError("settingsLoadFailed");
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

  useQuery({
    queryKey: ["trial-status"],
    queryFn: async () => {
      const { data, error } = await apiClient.GET("/api/v1/settings/provider/trial");
      if (error || !data) {
        setTrialStatus(null);
        throw new Error("trial status load failed");
      }
      setTrialStatus(data);
      return data;
    },
  });

  async function onEnableTrial() {
    const { data, error } = await apiClient.POST("/api/v1/settings/provider/trial");
    if (error || !data) {
      setTrialMessage("trialEnableFailed");
      return;
    }
    setTrialStatus(data);
    setTrialMessage(null);
  }

  async function onExitTrial() {
    const { data, error } = await apiClient.DELETE("/api/v1/settings/provider/trial");
    if (error || !data) {
      setTrialMessage("trialExitFailed");
      return;
    }
    setTrialStatus(data);
    setTrialMessage(null);
  }

  function onLocaleKeyDown(event: KeyboardEvent<HTMLElement>) {
    const currentIndex = localeOptions.findIndex((option) => option.value === locale);
    const lastIndex = localeOptions.length - 1;
    let nextIndex: number;
    switch (event.key) {
      case "ArrowLeft":
      case "ArrowUp":
        nextIndex = currentIndex <= 0 ? lastIndex : currentIndex - 1;
        break;
      case "ArrowRight":
      case "ArrowDown":
        nextIndex = currentIndex >= lastIndex ? 0 : currentIndex + 1;
        break;
      case "Home":
        nextIndex = 0;
        break;
      case "End":
        nextIndex = lastIndex;
        break;
      default:
        return;
    }
    event.preventDefault();
    setLocale(localeOptions[nextIndex].value);
    radioRefs.current[nextIndex]?.focus();
  }

  async function onSave(values: ProviderSettingsValues) {
    const parsed = createProviderFormSchema(copy).safeParse(values);
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
      setSaveMessage("saveFailed");
      return;
    }
    setSaveMessage("settingsSaved");
    await queryClient.invalidateQueries({ queryKey: ["provider-settings"] });
    // Saving personal provider params auto-exits trial mode (T30-TRIAL-004).
    await queryClient.invalidateQueries({ queryKey: ["trial-status"] });
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
      setKeyMessage("saveFailed");
      return;
    }
    setKeyStatus(data);
    if (keyInputRef.current) {
      keyInputRef.current.value = "";
    }
    setKeyMessage("settingsSaved");
    // Saving a personal API key also auto-exits trial mode (T30-TRIAL-004).
    await queryClient.invalidateQueries({ queryKey: ["trial-status"] });
  }

  async function onDeleteKey() {
    const { data, error } = await apiClient.DELETE("/api/v1/settings/provider/key");
    if (error || !data) {
      setKeyMessage("deleteFailed");
      return;
    }
    setKeyStatus(data);
    setKeyMessage("settingsSaved");
  }

  return (
    <main className="settings-page">
      <div className="page-header">
        <div>
          <p className="eyebrow">{copy.eyebrowSettings}</p>
          <h1>{copy.settingsTitle}</h1>
          <p className="page-subtitle">{copy.settingsSubtitle}</p>
        </div>
        <span className="settings-mark" aria-hidden="true">⚙</span>
      </div>
      {loadError && <div className="status-banner status-error">{copy[loadError]}</div>}

      <form onSubmit={handleSubmit(onSave)} className="paper-panel settings-form">
        <div className="panel-section-heading">
          <div>
            <p className="eyebrow">{copy.eyebrowModelRouting}</p>
            <h2>{copy.providerParamsTitle}</h2>
          </div>
          <span className="field-counter">{copy.localOnly}</span>
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
        {saveMessage && <p role="status">{copy[saveMessage]}</p>}
        <button className="btn btn-primary" type="submit" disabled={formState.isSubmitting}>
          {copy.saveSettings}
        </button>
      </form>

      <section className="paper-panel settings-key-panel" aria-label={copy.apiKeyStatusLabel}>
        <div className="panel-section-heading">
          <div>
            <p className="eyebrow">{copy.eyebrowSecret}</p>
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
        {keyMessage && <p role="status">{copy[keyMessage]}</p>}
        <button className="btn btn-primary" type="button" onClick={onSaveKey}>
          {copy.saveApiKey}
        </button>
        <button className="btn btn-danger" type="button" onClick={onDeleteKey}>
          {copy.deleteApiKey}
        </button>
      </section>

      <section
        className="paper-panel settings-language-panel"
        aria-labelledby="language-section-title"
      >
        <div className="panel-section-heading">
          <div>
            <p className="eyebrow">{copy.eyebrowLanguage}</p>
            <h2 id="language-section-title">{copy.languageSectionTitle}</h2>
          </div>
          <span className="field-counter">{copy.localOnly}</span>
        </div>
        <p className="settings-language-description">{copy.languageSectionDescription}</p>
        <div
          className="language-toggle"
          role="radiogroup"
          aria-label={copy.languageSectionTitle}
          onKeyDown={onLocaleKeyDown}
        >
          {localeOptions.map((option, index) => {
            const selected = option.value === locale;
            const label =
              option.value === "zh-CN" ? copy.languageChineseLabel : copy.languageEnglishLabel;
            return (
              <button
                key={option.value}
                type="button"
                role="radio"
                aria-checked={selected}
                aria-label={label}
                tabIndex={selected ? 0 : -1}
                className={`btn ${selected ? "btn-primary" : "btn-ghost"}`}
                onClick={() => setLocale(option.value)}
                ref={(element) => {
                  radioRefs.current[index] = element;
                }}
              >
                {option.label}
              </button>
            );
          })}
        </div>
      </section>

      <section
        className="paper-panel settings-trial-panel"
        aria-labelledby="trial-section-title"
      >
        <div className="panel-section-heading">
          <div>
            <p className="eyebrow">{copy.eyebrowTrial}</p>
            <h2 id="trial-section-title">{copy.trialSectionTitle}</h2>
          </div>
          {trialStatus && <span className="field-counter">{copy.localOnly}</span>}
        </div>
        <p className="settings-trial-description">{copy.trialSectionDescription}</p>
        {trialStatus && (
          <div className="settings-trial-controls">
            {!trialStatus.available ? (
              <p className="status-banner status-warning" role="status">
                {copy.trialUnavailable}
              </p>
            ) : trialStatus.enabled ? (
              <>
                <p className="status-banner status-error" role="status">
                  {trialStatus.remaining > 0
                    ? copy.trialEnabledStatus.replace(
                        "{remaining}",
                        String(trialStatus.remaining),
                      )
                    : copy.trialLimitReached}
                </p>
                <button className="btn btn-ghost" type="button" onClick={onExitTrial}>
                  {copy.trialExitButton}
                </button>
              </>
            ) : keyStatus?.apiKeyConfigured ? (
              <p className="status-banner status-info" role="status">
                {trialStatus.remaining > 0
                  ? copy.trialConfiguredPriorityStatus.replace(
                      "{remaining}",
                      String(trialStatus.remaining),
                    )
                  : copy.trialConfiguredExhausted}
              </p>
            ) : (
              <button className="btn btn-primary" type="button" onClick={onEnableTrial}>
                {copy.trialEnableButton}
              </button>
            )}
          </div>
        )}
        {trialMessage && <p role="status">{copy[trialMessage]}</p>}
      </section>
    </main>
  );
}
