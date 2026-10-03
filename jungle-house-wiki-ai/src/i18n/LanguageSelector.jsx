import { useEffect, useRef, useState } from 'react';
import { useLanguage } from './LanguageContext';
import { LANGUAGE_OPTIONS } from './translations';
import './LanguageSelector.css';

function GlobeIcon() {
  return (
    <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor"
      strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <circle cx="12" cy="12" r="9" />
      <path d="M3 12h18" />
      <path d="M12 3a14 14 0 0 1 0 18 14 14 0 0 1 0-18" />
    </svg>
  );
}

/* Compact globe + code button that opens a small list of languages.
   `placement` controls which way the list opens ('down' in headers, 'up' in
   footers). Colours come from the surrounding theme tokens. */
export default function LanguageSelector({ placement = 'down', className = '', showLabel = true }) {
  const { language, setLanguage, t } = useLanguage();
  const [open, setOpen] = useState(false);
  const rootRef = useRef(null);
  const current = LANGUAGE_OPTIONS.find((item) => item.code === language) || LANGUAGE_OPTIONS[0];

  useEffect(() => {
    if (!open) return undefined;
    const onPointerDown = (event) => {
      if (rootRef.current && !rootRef.current.contains(event.target)) setOpen(false);
    };
    const onKeyDown = (event) => {
      if (event.key === 'Escape') setOpen(false);
    };
    document.addEventListener('mousedown', onPointerDown);
    document.addEventListener('touchstart', onPointerDown);
    document.addEventListener('keydown', onKeyDown);
    return () => {
      document.removeEventListener('mousedown', onPointerDown);
      document.removeEventListener('touchstart', onPointerDown);
      document.removeEventListener('keydown', onKeyDown);
    };
  }, [open]);

  const choose = (code) => {
    setLanguage(code);
    setOpen(false);
  };

  return (
    <div ref={rootRef} className={`jh-lang ${className}`} data-placement={placement}>
      <button
        type="button"
        className="jh-lang-trigger"
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-label={`${t('common.chooseLanguage')}: ${current.label}`}
        title={t('common.chooseLanguage')}
        onClick={() => setOpen((value) => !value)}
      >
        <GlobeIcon />
        {showLabel ? <span className="jh-lang-code">{current.short}</span> : null}
      </button>

      {open ? (
        <ul className="jh-lang-menu" role="listbox" aria-label={t('common.chooseLanguage')}>
          {LANGUAGE_OPTIONS.map((option) => (
            <li key={option.code} role="presentation">
              <button
                type="button"
                role="option"
                aria-selected={option.code === language}
                lang={option.htmlLang}
                className={`jh-lang-option ${option.code === language ? 'is-selected' : ''}`}
                onClick={() => choose(option.code)}
              >
                <span className="jh-lang-option-label">{option.label}</span>
                <span className="jh-lang-option-check" aria-hidden="true">
                  {option.code === language ? '✓' : ''}
                </span>
              </button>
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}
