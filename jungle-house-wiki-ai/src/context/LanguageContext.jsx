/* eslint-disable react-refresh/only-export-components */

import { createContext, useCallback, useContext, useMemo, useState } from 'react';
import translations, { SUPPORTED_LANGUAGES } from '../i18n/translations';

const LanguageContext = createContext(null);

const STORAGE_KEY = 'jh_ui_language';
const SUPPORTED_CODES = new Set(SUPPORTED_LANGUAGES.map((entry) => entry.code));

function readStoredLanguage() {
  try {
    const stored = localStorage.getItem(STORAGE_KEY);
    return SUPPORTED_CODES.has(stored) ? stored : 'en';
  } catch {
    return 'en';
  }
}

export function LanguageProvider({ children }) {
  const [language, setLanguageState] = useState(readStoredLanguage);

  const setLanguage = useCallback((code) => {
    const next = SUPPORTED_CODES.has(code) ? code : 'en';
    setLanguageState(next);
    try {
      localStorage.setItem(STORAGE_KEY, next);
    } catch {
      // Private browsing / storage disabled -- the language still applies
      // for this session, it just will not be remembered next visit.
    }
  }, []);

  // t(key, vars?) looks up `key` in the active language, falls back to
  // English, then to the raw key itself so a missing translation renders
  // something visible instead of crashing. {placeholder} tokens in the
  // string are replaced from `vars`, e.g. t('dashboard.greeting', { name }).
  const t = useCallback(
    (key, vars) => {
      const template =
        translations[language]?.[key] ?? translations.en?.[key] ?? key;

      if (!vars) return template;

      return Object.keys(vars).reduce(
        (text, varKey) => text.replaceAll(`{${varKey}}`, String(vars[varKey])),
        template
      );
    },
    [language]
  );

  const value = useMemo(
    () => ({ language, setLanguage, t, languages: SUPPORTED_LANGUAGES }),
    [language, setLanguage, t]
  );

  return <LanguageContext.Provider value={value}>{children}</LanguageContext.Provider>;
}

export function useLanguage() {
  const context = useContext(LanguageContext);
  if (!context) {
    throw new Error('useLanguage must be used within a LanguageProvider');
  }
  return context;
}
