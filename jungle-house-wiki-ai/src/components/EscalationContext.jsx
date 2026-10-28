import { API_BASE_URL } from '../services/api';
import { useLanguage } from '../i18n/LanguageContext';

const LABELS = {
  en: { title: 'Relevant discussion', notice: 'Client-provided excerpts and description. Not an independently verified server transcript; assistant replies are not approved policy.', trigger: 'Triggering question', issue: 'Issue description', reason: 'Escalation reason', unknown: 'Time not recorded', user: 'Staff', assistant: 'Assistant', attachment: 'Attachment', omitted: 'Some relevant messages were omitted due to size limits.', shortened: 'Excerpt shortened' },
  zh: { title: '相关讨论', notice: '以下摘录和描述由客户端提供，未经服务器独立核实；助手回答不等于已批准的公司政策。', trigger: '触发升级的问题', issue: '议题描述', reason: '升级原因', unknown: '未记录时间', user: '员工', assistant: '助手', attachment: '附件', omitted: '受大小限制，部分相关消息未包含在内。', shortened: '摘录已缩短' },
  ms: { title: 'Perbincangan berkaitan', notice: 'Petikan dan penerangan daripada klien, bukan transkrip pelayan yang disahkan. Jawapan pembantu bukan polisi yang diluluskan.', trigger: 'Soalan pencetus', issue: 'Penerangan isu', reason: 'Sebab eskalasi', unknown: 'Masa tidak direkodkan', user: 'Kakitangan', assistant: 'Pembantu', attachment: 'Lampiran', omitted: 'Sesetengah mesej berkaitan tidak disertakan kerana had saiz.', shortened: 'Petikan dipendekkan' },
};

const REASONS = {
  en: { requested: 'Staff requested a team lead after reviewing suggestions.', rejected: 'Staff said the previous answer did not resolve the issue.', repeated: 'The issue remains unresolved after repeated attempts.', unavailable: 'The system could not provide an answer.', unconfirmed: 'An answer could not be confirmed from the available knowledge.' },
  zh: { requested: '员工查看建议后要求 Team Lead 协助。', rejected: '员工表示先前回答未能解决问题。', repeated: '多次尝试后问题仍未解决。', unavailable: '系统未能提供回答。', unconfirmed: '无法根据现有知识确认答案。' },
  ms: { requested: 'Kakitangan meminta bantuan ketua pasukan selepas menyemak cadangan.', rejected: 'Kakitangan menyatakan jawapan sebelumnya tidak menyelesaikan isu.', repeated: 'Isu masih belum selesai selepas beberapa percubaan.', unavailable: 'Sistem tidak dapat memberikan jawapan.', unconfirmed: 'Jawapan tidak dapat disahkan daripada pengetahuan yang tersedia.' },
};

const HISTORY_LABELS = {
  en: { short: 'Short chat history', more: 'View saved relevant messages', missing: 'No discussion snapshot is saved for this ticket. It may be an older ticket or the snapshot could not be saved.', gap: 'More messages are available in the relevant history below.' },
  zh: { short: '简短对话', more: '展开已保存的相关原文', missing: '此工单没有已保存的讨论快照，可能是旧工单或当时保存失败。', gap: '中间的更多相关消息可在下方展开查看。' },
  ms: { short: 'Sejarah sembang ringkas', more: 'Lihat mesej berkaitan yang disimpan', missing: 'Tiada petikan perbincangan disimpan untuk tiket ini. Ia mungkin tiket lama atau petikan gagal disimpan.', gap: 'Mesej tambahan boleh dilihat dalam sejarah berkaitan di bawah.' },
};

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

export default function EscalationContext({ context }) {
  const { language, locale } = useLanguage();
  const labels = LABELS[language] || LABELS.en;
  const historyLabels = HISTORY_LABELS[language] || HISTORY_LABELS.en;
  if (!context || context.provenance !== 'client_supplied_unverified' || !Array.isArray(context.messages)) {
    return <section className="card-like top-gap-sm"><p className="eyebrow">{labels.title}</p><p className="muted small">{historyLabels.missing}</p></section>;
  }
  const reasons = REASONS[language] || REASONS.en;
  const source = String(context.reason || '');
  const reason = source === 'staff_requested_escalation' ? reasons.requested
    : source === 'staff_not_satisfied_escalated' ? reasons.rejected
      : /repeated|after_two/.test(source) ? reasons.repeated
        : /system_error|unavailable/.test(source) ? reasons.unavailable : reasons.unconfirmed;
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
      <p><strong>{labels.trigger}:</strong> {context.trigger_question}</p>
      <p><strong>{labels.reason}:</strong> {reason}</p>
      <p><strong>{historyLabels.short}</strong></p>
      <ConversationMessages messages={previewMessages} labels={labels} locale={locale} attachmentBase={attachmentBase} preview />
      {previewMessages.length < context.messages.length ? <p className="muted small">{historyLabels.gap}</p> : null}
      {context.omitted_messages > 0 ? <p role="status">{labels.omitted} ({context.omitted_messages})</p> : null}
      <details>
        <summary>{historyLabels.more} ({context.messages.length})</summary>
        <p style={{ whiteSpace: 'pre-wrap' }}><strong>{labels.issue}:</strong> {context.description}</p>
        <ConversationMessages messages={context.messages} labels={labels} locale={locale} attachmentBase={attachmentBase} />
      </details>
    </section>
  );
}
