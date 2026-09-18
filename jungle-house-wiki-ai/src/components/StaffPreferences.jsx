/* Staff presentation preferences: browser-only, per-user. No backend requests.
   The language picker translates the staff navigation/settings UI only; AI/SOP
   translations are intentionally left for the planned multilingual backend. */
/* eslint-disable react-refresh/only-export-components */
import { createContext, useContext, useEffect, useMemo, useRef, useState } from 'react';

const PreferencesContext = createContext(null);
const INITIAL = Object.freeze({ appearance: 'light', contrast: 'system', accent: 'forest', language: 'en' });
const VALID = {
  appearance: ['light', 'dark', 'system'],
  contrast: ['system', 'medium', 'increased'],
  accent: ['forest', 'honey', 'ocean', 'orchid'],
  language: ['en', 'zh', 'ms'],
};

const translations = {
  en: {
    assistant: 'Staff Assistant', workspace: 'Staff workspace', newChat: 'New chat', searchChats: 'Search chats',
    knowledge: 'Knowledge Base', quiz: 'Training & Quiz', messages: 'Messages', notifications: 'Notifications',
    more: 'More', profile: 'My profile', account: 'Profile & account', sop: 'SOP selection', history: 'Full chat history',
    recent: 'Recent chats', allChats: 'See all conversations', emptyChats: 'Your conversations appear here.',
    logout: 'Log out', loggingOut: 'Logging out…', settings: 'Appearance & language', settingsTitle: 'Your workspace',
    settingsSubtitle: 'Make your Jungle House experience your own.', appearance: 'Appearance',
    light: 'Light', dark: 'Dark', system: 'System', contrast: 'Contrast', medium: 'Medium',
    increased: 'Increased', accent: 'Accent colour', forest: 'Forest', honey: 'Honey', ocean: 'Ocean',
    orchid: 'Orchid', language: 'Interface language', preview: 'Your preview', sampleTitle: 'Knowledge, beautifully organised.',
    sampleDetail: 'A calmer space for every shift.', note: 'Language changes staff navigation and these settings only. AI responses, articles and other pages remain in their current language until multilingual support is implemented.',
    saved: 'Saved on this browser for your account.', close: 'Close preferences', searchPlaceholder: 'Search your conversations…', noMatches: 'No matching conversations.', viewHistory: 'View detailed chat history', openSettings: 'Open workspace preferences',
  },
  zh: {
    assistant: '员工智能助手', workspace: '员工工作空间', newChat: '新对话', searchChats: '搜索对话',
    knowledge: '知识库', quiz: '培训与测验', messages: '消息', notifications: '通知', more: '更多',
    profile: '我的个人资料', account: '个人资料与账户', sop: '标准作业程序', history: '完整聊天记录',
    recent: '最近对话', allChats: '查看所有对话', emptyChats: '您的对话将显示在这里。',
    logout: '退出登录', loggingOut: '正在退出…', settings: '外观与语言', settingsTitle: '您的工作空间',
    settingsSubtitle: '打造属于您的 Jungle House 工作体验。', appearance: '外观', light: '浅色',
    dark: '深色', system: '跟随系统', contrast: '对比度', medium: '标准', increased: '增强',
    accent: '主题色', forest: '森林绿', honey: '蜂蜜金', ocean: '海洋蓝', orchid: '兰花紫',
    language: '界面语言', preview: '预览效果', sampleTitle: '让知识井然有序。', sampleDetail: '每个班次，都更从容。',
    note: '目前仅翻译员工导航和此设置面板。AI 回复、文章及其他页面将在多语言后端完成后支持翻译。',
    saved: '设置已在此浏览器中按账户保存。', close: '关闭设置', searchPlaceholder: '搜索您的对话…', noMatches: '未找到匹配的对话。', viewHistory: '查看详细聊天记录', openSettings: '打开工作空间设置',
  },
  ms: {
    assistant: 'Pembantu Kakitangan', workspace: 'Ruang kerja kakitangan', newChat: 'Sembang baharu',
    searchChats: 'Cari sembang', knowledge: 'Pangkalan Pengetahuan', quiz: 'Latihan & Kuiz', messages: 'Mesej',
    notifications: 'Pemberitahuan', more: 'Lagi', profile: 'Profil saya', account: 'Profil & akaun',
    sop: 'Pilihan SOP', history: 'Sejarah sembang penuh', recent: 'Sembang terkini',
    allChats: 'Lihat semua perbualan', emptyChats: 'Perbualan anda akan dipaparkan di sini.',
    logout: 'Log keluar', loggingOut: 'Sedang log keluar…', settings: 'Paparan & bahasa',
    settingsTitle: 'Ruang kerja anda', settingsSubtitle: 'Sesuaikan pengalaman Jungle House anda.',
    appearance: 'Paparan', light: 'Cerah', dark: 'Gelap', system: 'Ikut sistem', contrast: 'Kontras',
    medium: 'Sederhana', increased: 'Dipertingkat', accent: 'Warna tema', forest: 'Hutan',
    honey: 'Madu', ocean: 'Lautan', orchid: 'Orkid', language: 'Bahasa antara muka',
    preview: 'Pratonton anda', sampleTitle: 'Pengetahuan yang tersusun.', sampleDetail: 'Ruang lebih tenang untuk setiap syif.',
    note: 'Buat masa ini, hanya navigasi kakitangan dan tetapan ini diterjemahkan. Jawapan AI, artikel dan halaman lain kekal dalam bahasa asal sehingga sokongan berbilang bahasa siap.',
    saved: 'Disimpan dalam pelayar ini untuk akaun anda.', close: 'Tutup tetapan',
    searchPlaceholder: 'Cari perbualan anda…', noMatches: 'Tiada perbualan sepadan.', viewHistory: 'Lihat sejarah sembang terperinci', openSettings: 'Buka tetapan ruang kerja',
  },
};

function normalizeSettings(candidate) {
  const settings = candidate && typeof candidate === 'object' ? candidate : {};
  return Object.fromEntries(Object.keys(INITIAL).map((key) => [key,
    VALID[key].includes(settings[key]) ? settings[key] : INITIAL[key],
  ]));
}

function storageKey(user) {
  const id = String(user?.id ?? 'guest').replace(/[^\w-]/g, '_');
  return `jh_staff_preferences_v1_${id}`;
}

function readSettings(user) {
  try { return normalizeSettings(JSON.parse(localStorage.getItem(storageKey(user)) || '{}')); }
  catch { return { ...INITIAL }; }
}

export function StaffPreferencesProvider({ user, children }) {
  const [settings, setSettings] = useState(() => readSettings(user));
  const [systemDark, setSystemDark] = useState(() =>
    typeof window !== 'undefined' && window.matchMedia?.('(prefers-color-scheme: dark)').matches);
  const [systemContrast, setSystemContrast] = useState(() =>
    typeof window !== 'undefined' && window.matchMedia?.('(prefers-contrast: more)').matches);

  useEffect(() => {
    try { localStorage.setItem(storageKey(user), JSON.stringify(settings)); }
    catch { /* Blocked storage should not prevent settings being used in this tab. */ }
  }, [settings, user]);

  useEffect(() => {
    if (typeof window === 'undefined' || !window.matchMedia) return undefined;
    const scheme = window.matchMedia('(prefers-color-scheme: dark)');
    const contrast = window.matchMedia('(prefers-contrast: more)');
    const onScheme = (event) => setSystemDark(event.matches);
    const onContrast = (event) => setSystemContrast(event.matches);
    scheme.addEventListener('change', onScheme);
    contrast.addEventListener('change', onContrast);
    return () => { scheme.removeEventListener('change', onScheme); contrast.removeEventListener('change', onContrast); };
  }, []);

  const setPreference = (name, value) => {
    if (!Object.prototype.hasOwnProperty.call(VALID, name) || !VALID[name].includes(value)) return;
    setSettings((current) => ({ ...current, [name]: value }));
  };

  const effectiveAppearance = settings.appearance === 'system'
    ? (systemDark ? 'dark' : 'light') : settings.appearance;
  const effectiveContrast = settings.contrast === 'system'
    ? (systemContrast ? 'increased' : 'medium') : settings.contrast;
  const t = (key) => translations[settings.language]?.[key] || translations.en[key] || key;
  const contextValue = useMemo(() => ({ settings, setPreference, effectiveAppearance, effectiveContrast, t }),
    // settings captures the language as well as all other preferences.
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [settings, effectiveAppearance, effectiveContrast]);
  return <PreferencesContext.Provider value={contextValue}>{children}</PreferencesContext.Provider>;
}

export function useStaffPreferences() {
  const context = useContext(PreferencesContext);
  if (!context) throw new Error('Staff preferences must be used within StaffPreferencesProvider.');
  return context;
}

const options = {
  appearance: ['light', 'dark', 'system'],
  contrast: ['system', 'medium', 'increased'],
  accent: ['forest', 'honey', 'ocean', 'orchid'],
};
const languageOptions = [
  { value: 'en', label: 'English' },
  { value: 'zh', label: '简体中文' },
  { value: 'ms', label: 'Bahasa Malaysia' },
];

export function StaffPreferencesDialog({ onClose }) {
  const { settings, setPreference, t, effectiveAppearance } = useStaffPreferences();
  const closeButton = useRef(null);
  useEffect(() => {
    const previous = document.activeElement;
    closeButton.current?.focus();
    const onKeyDown = (event) => { if (event.key === 'Escape') onClose(); };
    window.addEventListener('keydown', onKeyDown);
    return () => { window.removeEventListener('keydown', onKeyDown); previous?.focus?.(); };
  }, [onClose]);

  return (
    <div className="jh-preferences-backdrop" onMouseDown={(event) => {
      if (event.target === event.currentTarget) onClose();
    }}>
      <section className="jh-preferences-panel" role="dialog" aria-modal="true"
        aria-labelledby="jh-preferences-heading" lang={settings.language === 'zh' ? 'zh-Hans' : settings.language}>
        <div className="jh-preferences-hero">
          <div className="jh-preferences-hero-heading">
            <div className="jh-preferences-leaf" aria-hidden="true">✦</div>
            <div><span className="jh-preferences-eyebrow">JUNGLE HOUSE · PERSONALISE</span>
              <h2 id="jh-preferences-heading">{t('settingsTitle')}</h2>
              <p>{t('settingsSubtitle')}</p></div>
          </div>
          <button ref={closeButton} type="button" className="jh-preferences-close" onClick={onClose}
            aria-label={t('close')}>×</button>
        </div>
        <div className="jh-preferences-sections">
          <fieldset className="jh-preferences-group">
            <legend>{t('appearance')}</legend>
            <div className="jh-appearance-choices">
              {options.appearance.map((value) => <label key={value} className={`jh-appearance-choice ${settings.appearance === value ? 'selected' : ''}`}>
                <input type="radio" name="jh-appearance" checked={settings.appearance === value}
                  onChange={() => setPreference('appearance', value)} />
                <span className={`jh-appearance-thumb is-${value}`} aria-hidden="true"><i/><b/><em/></span>
                <span>{t(value)}</span>
                <span className="jh-choice-check" aria-hidden="true">{settings.appearance === value ? '✓' : ''}</span>
              </label>)}
            </div>
          </fieldset>
          <fieldset className="jh-preferences-group">
            <legend>{t('contrast')}</legend>
            <div className="jh-segmented">
              {options.contrast.map((value) => <label key={value} className={settings.contrast === value ? 'selected' : ''}>
                <input type="radio" name="jh-contrast" checked={settings.contrast === value}
                  onChange={() => setPreference('contrast', value)} /><span>{t(value)}</span>
              </label>)}
            </div>
          </fieldset>
          <fieldset className="jh-preferences-group">
            <legend>{t('accent')}</legend>
            <div className="jh-accent-choices">
              {options.accent.map((value) => <label key={value} className={settings.accent === value ? 'selected' : ''}>
                <input type="radio" name="jh-accent" checked={settings.accent === value}
                  onChange={() => setPreference('accent', value)} />
                <span className={`jh-accent-dot is-${value}`} aria-hidden="true"/><span>{t(value)}</span>
                <span aria-hidden="true">{settings.accent === value ? '✓' : ''}</span>
              </label>)}
            </div>
          </fieldset>
          <fieldset className="jh-preferences-group">
            <legend>{t('language')}</legend>
            <div className="jh-language-choices">
              {languageOptions.map(({value, label}) => <label key={value} className={settings.language === value ? 'selected' : ''}>
                <input type="radio" name="jh-language" checked={settings.language === value}
                  onChange={() => setPreference('language', value)} />
                <span>{label}</span><span aria-hidden="true">{settings.language === value ? '✓' : ''}</span>
              </label>)}
            </div>
            <p className="jh-preferences-note">{t('note')}</p>
          </fieldset>
          <div className="jh-preferences-preview" data-preview-theme={effectiveAppearance}>
            <span>{t('preview')}</span><strong>{t('sampleTitle')}</strong><small>{t('sampleDetail')}</small>
            <div className="jh-preview-progress"><i/></div>
          </div>
          <p className="jh-preferences-saved" role="status">✓ {t('saved')}</p>
        </div>
      </section>
    </div>
  );
}
