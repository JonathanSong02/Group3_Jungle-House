// A source identifies a code path, not verified policy or a server transcript.
const ANSWER_SOURCES = new Set([
  'wiki_article_database', 'ai_provider_answer', 'visual_image_match',
  'image_retrieval_knowledge_base', 'image_retrieval_approved_escalation',
  'manager_approved_review', 'team_lead',
]);
const UNCONFIRMED_SOURCES = new Set([
  'fallback', 'unknown', 'low_confidence_direct_escalation',
  'low_confidence_or_model_unavailable', 'generic_answer_escalated',
  'repeated_unclear_question', 'repeated_system_problem',
  'escalate_after_two_unclear_attempts', 'related_knowledge',
]);

export function escalationReasonKey(source) {
  if (source === 'staff_requested_escalation') return 'esc.evidence.requested';
  if (source === 'staff_not_satisfied_escalated') return 'esc.evidence.rejected';
  if (source === 'repeated_invalid_input') return 'esc.evidence.invalidInput';
  if (source === 'repeated_failed_answer' || source === 'escalate_after_two_unclear_attempts'
      || source === 'repeated_unclear_question' || source === 'repeated_system_problem') return 'esc.evidence.repeated';
  if (['system_error', 'engine_unavailable', 'prediction_error', 'pytorch_model_error'].includes(source)) return 'esc.evidence.systemError';
  if (UNCONFIRMED_SOURCES.has(source) || ANSWER_SOURCES.has(source)) return 'esc.evidence.unconfirmed';
  return 'esc.evidence.unknownReason';
}

export function hasDiscussion(context) {
  return Boolean(context && context.provenance === 'client_supplied_unverified'
    && Array.isArray(context.messages) && context.messages.length
    && context.messages.every((message) => message && ['user', 'assistant'].includes(message.role)
      && typeof message.content === 'string'));
}

export function discussionState(context, availability, loadStatus) {
  if (hasDiscussion(context)) return 'available';
  if (loadStatus === 'invalid_data' || context != null) return 'invalid';
  if (availability === 'unavailable' || loadStatus === 'read_failed') return 'readFailed';
  return 'missing'; // Includes legacy responses; absence does not prove capture failed.
}

export function previousResponseEvidence(ticket) {
  const value = typeof ticket.ai_answer === 'string' ? ticket.ai_answer.trim() : '';
  const source = typeof ticket.ai_source === 'string' ? ticket.ai_source : '';
  const systemNote = /^(?:Staff reviewed the suggested Knowledge Base articles|Staff said this previous AI answer|An internal system error occurred|I still could not understand|I could not find a confident answer after repeated attempts)/i.test(value);
  // Never parse a combined rejection narrative or pick the last snapshot reply.
  return { answer: value && ANSWER_SOURCES.has(source) && !systemNote ? value : '',
    note: value && (!ANSWER_SOURCES.has(source) || systemNote) ? value : '',
    hasAssistantExcerpts: hasDiscussion(ticket.conversation_context)
      && ticket.conversation_context.messages.some((message) => message.role === 'assistant') };
}
