import { useLanguage } from '../i18n/LanguageContext';

export default function StatusBadge({ status }) {
  const { tOr } = useLanguage();
  const tone = String(status || '').toLowerCase();
  // Known statuses are translated; anything else is shown exactly as stored.
  return <span className={`status-badge ${tone}`}>{tOr(`esc.status.${tone}`, status)}</span>;
}
