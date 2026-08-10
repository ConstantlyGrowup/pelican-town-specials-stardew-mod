import {
  createContext,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import {
  catalogs,
  DEFAULT_LOCALE,
  isLanguage,
  LOCALE_STORAGE_KEY,
  type Copy,
  type Language,
} from "./copy";

type LocaleContextValue = {
  locale: Language;
  setLocale: (next: Language) => void;
};

/**
 * The default context keeps `useCopy()` safe without a provider (tests render
 * pages bare): it resolves to `zh-CN` and `setLocale` is a no-op.
 */
const LocaleContext = createContext<LocaleContextValue>({
  locale: DEFAULT_LOCALE,
  setLocale: () => {},
});

function readStoredLocale(): Language {
  try {
    const stored = window.localStorage.getItem(LOCALE_STORAGE_KEY);
    if (isLanguage(stored)) {
      return stored;
    }
  } catch {
    // localStorage can be unavailable (private mode / sandboxed iframe).
  }
  return DEFAULT_LOCALE;
}

export function LocaleProvider({ children }: { children: ReactNode }) {
  const [locale, setLocaleState] = useState<Language>(readStoredLocale);

  // Keep the document language in sync so assistive tech and the browser
  // (translator, fonts, date formatting) use the selected locale.
  useEffect(() => {
    document.documentElement.lang = locale;
  }, [locale]);

  const value = useMemo<LocaleContextValue>(
    () => ({
      locale,
      setLocale: (next) => {
        setLocaleState(next);
        try {
          window.localStorage.setItem(LOCALE_STORAGE_KEY, next);
        } catch {
          // Persisting is best-effort; the in-memory choice still applies.
        }
      },
    }),
    [locale],
  );

  return (
    <LocaleContext.Provider value={value}>{children}</LocaleContext.Provider>
  );
}

export function useLocale(): Language {
  return useContext(LocaleContext).locale;
}

/** The locale setter, split out so callers can update the preference. */
export function useSetLocale(): (next: Language) => void {
  return useContext(LocaleContext).setLocale;
}

export function useCopy(): Copy {
  return catalogs[useContext(LocaleContext).locale];
}
