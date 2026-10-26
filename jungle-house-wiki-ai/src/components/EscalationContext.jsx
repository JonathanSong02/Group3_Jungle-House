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

export default function EscalationContext({ context }) {
  const { language, locale } = useLanguage();
  if (!context || context.provenance !== 'client_supplied_unverified' || !Array.isArray(context.messages)) return null;
  const labels = LABELS[language] || LABELS.en;
  const reasons = REASONS[language] || REASONS.en;
  const source = String(context.reason || '');
  const reason = source === 'staff_requested_escalation' ? reasons.requested
    : source === 'staff_not_satisfied_escalated' ? reasons.rejected
      : /repeated|after_two/.test(source) ? reasons.repeated
        : /system_error|unavailable/.test(source) ? reasons.unavailable : reasons.unconfirmed;
  const attachmentBase = API_BASE_URL.startsWith('http') ? API_BASE_URL.replace(/\/api\/?$/, '') : '';
  return (
    <details className="card-like top-gap-sm" style={{ overflowWrap: 'anywhere' }}>
      <summary>{labels.title}</summary>
      <p className="muted small">{labels.notice}</p>
      <p><strong>{labels.trigger}:</strong> {context.trigger_question}</p>
      <p style={{ whiteSpace: 'pre-wrap', overflowWrap: 'anywhere' }}><strong>{labels.issue}:</strong> {context.description}</p>
      <p><strong>{labels.reason}:</strong> {reason}</p>
      {context.omitted_messages > 0 ? <p role="status">{labels.omitted} ({context.omitted_messages})</p> : null}
      <ol>
        {context.messages.map((message, index) => {
          const time = message.timestamp ? new Date(message.timestamp) : null;
          return (
            <li key={index}>
              <strong>{message.role === 'user' ? labels.user : labels.assistant}</strong>
              {' · '}{time && !Number.isNaN(time.getTime()) ? time.toLocaleString(locale) : labels.unknown}
              <p style={{ whiteSpace: 'pre-wrap', overflowWrap: 'anywhere' }}>{message.content}</p>
              {message.truncated ? <small>{labels.shortened}</small> : null}
              {(message.attachments || []).filter((path) => /^\/static\/uploads\/chat\/[A-Za-z0-9_.-]+$/.test(path) && !path.includes('..')).map((path) => (
                <p key={path}><a href={`${attachmentBase}${path}`} target="_blank" rel="noreferrer">{labels.attachment}</a></p>
              ))}
            </li>
          );
        })}
      </ol>
    </details>
  );
}
