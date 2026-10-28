import { useLanguage } from '../i18n/LanguageContext';

// Small "Notion" label for an article synced from Notion. Hidden while the
// article is still in the 'Notion' category itself -- the category label
// already says so. Each page passes one of its own existing pill classes so
// the label follows that page's theme (light/dark included).
export default function SourceBadge({ article, className = '' }) {
  const { t } = useLanguage();

  const fromNotion = String(article?.source_type || '').trim().toLowerCase() === 'notion';
  const stillUncategorized = String(article?.category || '').trim().toLowerCase() === 'notion';

  if (!fromNotion || stillUncategorized) return null;

  return (
    <span className={className} title={t('source.notionTitle')}>
      {t('source.notion')}
    </span>
  );
}
