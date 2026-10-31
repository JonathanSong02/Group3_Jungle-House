const SAVE_STATUSES = new Set(['saved', 'not_provided', 'invalid_context', 'schema_missing',
  'storage_permission_denied', 'storage_unavailable', 'owner_mismatch', 'issue_mismatch']);

export function escalationMetadata(data) {
  const value = data?.escalation_id;
  const id = (typeof value === 'number' || (typeof value === 'string' && /^[1-9]\d*$/.test(value))) ? Number(value) : null;
  if (!Number.isSafeInteger(id) || id <= 0) return {};
  const status = SAVE_STATUSES.has(data.escalation_context_status) ? data.escalation_context_status : '';
  return { escalation_id: id,
    escalation_context_saved: typeof data.escalation_context_saved === 'boolean' ? data.escalation_context_saved : undefined,
    escalation_context_status: status,
    // Store only a safe marker, never a raw server error or diagnostic message.
    escalation_context_warning: status !== 'not_provided'
      && (data.escalation_context_saved === false || Boolean(data.escalation_context_warning)),
  };
}

export function normalizeEscalationResponse(data, t) {
  const failed = data && (data.source === 'escalation_save_failed'
    || (data.escalation_id === null && (data.escalation || data.escalation_ready || data.escalation_required)));
  if (!failed) return data;
  const message = t('chat.ticketSaveFailed');
  return { ...data, escalation_id: null, source: 'escalation_save_failed', type: 'text',
    reply: message, answer: message, message, fallback_message: message, fallback: true,
    escalation: false, escalation_ready: false, escalation_required: false, options: [], steps: [] };
}

export function escalationErrorInfo(error, t) {
  const data = error?.response?.data;
  if (!data || typeof data !== 'object'
      || (!Object.hasOwn(data, 'escalation_id') && data.source !== 'escalation_save_failed')) return null;
  const metadata = escalationMetadata(data);
  const text = metadata.escalation_id ? t('chat.ticketErrorSaved', { id: metadata.escalation_id })
    : t(data.source === 'escalation_save_failed' ? 'chat.ticketSaveFailed' : 'chat.ticketErrorUnknown');
  return { ...metadata, escalation_request_failed: true, text };
}
