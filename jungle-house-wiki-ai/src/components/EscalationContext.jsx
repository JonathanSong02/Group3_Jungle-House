import { API_BASE_URL } from '../services/api';
import { useLanguage } from '../i18n/LanguageContext';
import { discussionState, escalationReasonKey } from '../utils/escalationEvidence';

function ConversationMessages({ messages, labels, locale, attachmentBase, preview = false }) {
  return <ol>{messages.map((message, index) => {
    const time = message.timestamp ? new Date(message.timestamp) : null;
    const content = String(message.content || '');
    const shortened = preview && content.length > 320;
    return <li key={index}>
      <strong>{message.role === 'user' ? labels.user : labels.assistant}</strong>
      {' · '}{time && !Number.isNaN(time.getTime()) ? time.toLocaleString(locale) : labels.unknown}
      <p style={{ whiteSpace: 'pre-wrap', overflowWrap: 'anywhere' }}>{shortened ? `${content.slice(0, 320)}…` : content}</p>
      {message.truncated || shortened ? <small>{labels.shortened}</small> : null}
      {(Array.isArray(message.attachments) ? message.attachments : []).filter((path) => /^\/static\/uploads\/chat\/[A-Za-z0-9_.-]+$/.test(path) && !path.includes('..')).map((path) => (
        <p key={path}><a href={`${attachmentBase}${path}`} target="_blank" rel="noreferrer">{labels.attachment}</a></p>
      ))}
    </li>;
  })}</ol>;
}

export default function EscalationContext({ context, availability, loadStatus, showReason = true }) {
  const { t, locale } = useLanguage();
  const labels = Object.fromEntries(['title', 'notice', 'trigger', 'issue', 'unknown', 'user', 'assistant', 'attachment', 'omitted', 'shortened']
    .map((key) => [key, t(`esc.discussion.${key}`)]));
  const state = discussionState(context, availability, loadStatus);
  if (state !== 'available') {
    return <section className="card-like top-gap-sm"><p className="eyebrow">{labels.title}</p><p className="muted small" role="status">{t(`esc.discussion.${state}`)}</p></section>;
  }
  const attachmentBase = API_BASE_URL.startsWith('http') ? API_BASE_URL.replace(/\/api\/?$/, '') : '';
  const firstStaff = context.messages.findIndex((message) => message.role === 'user');
  const firstAnswer = context.messages.findIndex((message, index) => index > firstStaff && message.role === 'assistant');
  const correction = context.messages.findLastIndex((message) => message.role === 'user' && /^(?:i mean\b|correction\b|actually\b|maksud saya|sebenarnya|更正|纠正|糾正|其实|其實|我是说|我是說)/i.test(message.content));
  const tailStart = Math.max(0, context.messages.length - (correction >= 0 ? 2 : 3));
  const indices = [...new Set([firstStaff, firstAnswer, correction, correction >= 0 ? correction + 1 : -1, ...context.messages.slice(tailStart).map((_, index) => tailStart + index)])]
    .filter((index) => index >= Math.max(0, firstStaff) && index < context.messages.length).sort((a, b) => a - b);
  const previewMessages = indices.map((index) => context.messages[index]);
  return (
    <section className="card-like top-gap-sm" style={{ overflowWrap: 'anywhere' }}>
      <p className="eyebrow">{labels.title}</p>
      <p className="muted small">{labels.notice}</p>
      <p><strong>{labels.trigger}:</strong> {typeof context.trigger_question === 'string' ? context.trigger_question : ''}</p>
      {showReason ? <p><strong>{t('esc.evidence.why')}:</strong> {t(escalationReasonKey(context.reason))}</p> : null}
      <p><strong>{t('esc.discussion.short')}</strong></p>
      <ConversationMessages messages={previewMessages} labels={labels} locale={locale} attachmentBase={attachmentBase} preview />
      {previewMessages.length < context.messages.length ? <p className="muted small">{t('esc.discussion.gap')}</p> : null}
      {context.omitted_messages > 0 ? <p role="status">{labels.omitted} ({context.omitted_messages})</p> : null}
      <details>
        <summary>{t('esc.discussion.more')} ({context.messages.length})</summary>
        <p style={{ whiteSpace: 'pre-wrap' }}><strong>{labels.issue}:</strong> {typeof context.description === 'string' ? context.description : ''}</p>
        <ConversationMessages messages={context.messages} labels={labels} locale={locale} attachmentBase={attachmentBase} />
      </details>
    </section>
  );
}
