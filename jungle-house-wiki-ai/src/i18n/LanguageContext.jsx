/* Lightweight app-wide language state: { language, setLanguage, t }.
   Browser-only (localStorage); no API calls, no backend dependency. */
/* eslint-disable react-refresh/only-export-components */
import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';
import {
  DEFAULT_LANGUAGE,
  LANGUAGE_OPTIONS,
  SUPPORTED_LANGUAGES,
  translations,
} from './translations';

export const LANGUAGE_STORAGE_KEY = 'jungle_house_lang';

const LanguageContext = createContext(null);

function isSupported(value) {
  return SUPPORTED_LANGUAGES.includes(value);
}

// A missing, blocked or corrupted stored value resets to English.
function readStoredLanguage() {
  try {
    const stored = window.localStorage.getItem(LANGUAGE_STORAGE_KEY);
    if (isSupported(stored)) return stored;
    if (stored !== null) window.localStorage.setItem(LANGUAGE_STORAGE_KEY, DEFAULT_LANGUAGE);
  } catch {
    /* Storage can be blocked (private mode); the in-memory default still works. */
  }
  return DEFAULT_LANGUAGE;
}

function interpolate(template, vars) {
  if (!vars) return template;
  return template.replace(/\{(\w+)\}/g, (match, name) =>
    (vars[name] === undefined || vars[name] === null ? match : String(vars[name])));
}

export function LanguageProvider({ children }) {
  const [language, setLanguageState] = useState(readStoredLanguage);

  const setLanguage = useCallback((next) => {
    if (!isSupported(next)) return;
    setLanguageState(next);
    try { window.localStorage.setItem(LANGUAGE_STORAGE_KEY, next); }
    catch { /* Keep working for this tab even if the choice cannot be saved. */ }
  }, []);

  // Keep several open tabs in step.
  useEffect(() => {
    const onStorage = (event) => {
      if (event.key === LANGUAGE_STORAGE_KEY && isSupported(event.newValue)) {
        setLanguageState(event.newValue);
      }
    };
    window.addEventListener('storage', onStorage);
    return () => window.removeEventListener('storage', onStorage);
  }, []);

  // <html lang> improves screen readers and lets CSS pick CJK-safe fonts.
  useEffect(() => {
    const option = LANGUAGE_OPTIONS.find((item) => item.code === language);
    document.documentElement.setAttribute('lang', option?.htmlLang || DEFAULT_LANGUAGE);
    document.documentElement.setAttribute('data-lang', language);
  }, [language]);

  const value = useMemo(() => {
    const dictionary = translations[language] || translations[DEFAULT_LANGUAGE];
    const english = translations[DEFAULT_LANGUAGE];

    // t('key', { n: 3 }): selected language -> English -> the key itself.
    const t = (key, vars) => {
      const text = dictionary[key] ?? english[key];
      return typeof text === 'string' ? interpolate(text, vars) : String(key);
    };
    // tOr('dashboard.stat.' + label, label): for keys built from API data, where an
    // unknown value should be shown as-is rather than as a raw key.
    const tOr = (key, fallback) => dictionary[key] ?? english[key] ?? fallback;

    return { language, setLanguage, t, tOr };
  }, [language, setLanguage]);

  return <LanguageContext.Provider value={value}>{children}</LanguageContext.Provider>;
}

export function useLanguage() {
  const context = useContext(LanguageContext);
  if (context) return context;
  // Outside a provider (isolated render/test) behave as English instead of crashing.
  const english = translations[DEFAULT_LANGUAGE];
  return {
    language: DEFAULT_LANGUAGE,
    setLanguage: () => {},
    t: (key, vars) => interpolate(english[key] ?? String(key), vars),
    tOr: (key, fallback) => english[key] ?? fallback,
  };
}
