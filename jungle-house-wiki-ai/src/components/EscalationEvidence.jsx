import { useLanguage } from '../i18n/LanguageContext';
import { escalationReasonKey, previousResponseEvidence } from '../utils/escalationEvidence';

export default function EscalationEvidence({ ticket }) {
  const { t } = useLanguage();
  const evidence = previousResponseEvidence(ticket);
  const source = ticket.ai_source || ticket.conversation_context?.reason;
  return <>
    <section className="card-like top-gap-sm" style={{ overflowWrap: 'anywhere' }}>
      <p className="eyebrow">{t('esc.evidence.previous')}</p>
      {evidence.answer ? <>
        <p style={{ whiteSpace: 'pre-wrap' }}>{evidence.answer}</p>
        <p className="muted small">{t('esc.evidence.recordedNotice')}</p>
      </> : <p className="muted small">{t('esc.evidence.noPrevious')}</p>}
      {evidence.hasAssistantExcerpts ? <p className="muted small">{t('esc.evidence.seeDiscussion')}</p> : null}
    </section>
    <section className="card-like top-gap-sm" style={{ overflowWrap: 'anywhere' }}>
      <p className="eyebrow">{t('esc.evidence.why')}</p>
      <p>{t(escalationReasonKey(source))}</p>
      {evidence.note ? <details>
        <summary>{t('esc.evidence.legacyNote')}</summary>
        <p className="muted small">{t('esc.evidence.noteNotice')}</p>
        <p style={{ whiteSpace: 'pre-wrap' }}>{evidence.note}</p>
      </details> : null}
    </section>
  </>;
}
