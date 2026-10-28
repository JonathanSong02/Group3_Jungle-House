import { useId } from 'react';
import { useLanguage } from '../i18n/LanguageContext';
import { QUESTION_LABELS } from '../utils/standardQuestionLabels';

export default function StandardQuestionField({ value, confirmed, onChange, onConfirm }) {
  const id = useId();
  const { language } = useLanguage();
  const labels = QUESTION_LABELS[language] || QUESTION_LABELS.en;
  return <div className="top-gap-sm" style={{ overflowWrap: 'anywhere' }}>
    <label htmlFor={id}><strong>{labels.title}</strong></label>
    <input id={id} type="text" required maxLength={255} value={value || ''} onChange={(event) => onChange(event.target.value)}
      style={{ width: '100%', boxSizing: 'border-box' }} aria-describedby={`${id}-hint`} />
    <p id={`${id}-hint`} className="muted small">{labels.hint}</p>
    <label style={{ display: 'flex', gap: '0.5rem', alignItems: 'flex-start' }}>
      <input type="checkbox" checked={Boolean(confirmed)} onChange={(event) => onConfirm(event.target.checked)} />
      <span>{labels.confirm}</span>
    </label>
  </div>;
}
