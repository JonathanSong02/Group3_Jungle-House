// Database responses are authoritative; localStorage is only an owner-scoped cache.
export function hydrateChat(detail, buildAiMessage, starterMessages) {
  const messages = [];
  for (const turn of detail.turns || []) {
    messages.push({ id: turn.message_id, server_message_id: turn.message_id, request_id: turn.request_id, sender: 'user', type: 'text',
      text: turn.question, image_files: turn.attachment?.url ? [turn.attachment.url] : [] });
    if (turn.response) messages.push({ ...buildAiMessage(turn.response), id: `${turn.message_id}:answer`,
      server_message_id: turn.message_id, reply_to_request_id: turn.request_id, issue_id: turn.response.issue_id });
    else messages.push({ id: `${turn.message_id}:status`, sender: 'ai', type: 'text',
      text: turn.status === 'pending' ? 'This message is still processing. Reopen this chat shortly to load its answer.' :
        'This message was saved, but processing failed. Please retry it.', pending_request: turn.request_id,
      retry_question: turn.question, reply_to_request_id: turn.request_id });
  }
  return { id: String(detail.chat_id), title: detail.title, latest_message_id: detail.latest_message_id,
    messages: messages.length ? messages : starterMessages, turns: detail.turns || [] };
}

export function reconcileHydration(current, incoming) {
  if (current.latest_message_id && !incoming.turns.some((turn) => turn.message_id === current.latest_message_id)) return current;
  const answers = new Map(current.messages.filter((m) => m.server_message_id && m.reply_to_request_id)
    .map((m) => [m.reply_to_request_id, m]));
  return { ...current, ...incoming, messages: incoming.messages.map((m) =>
    m.pending_request && answers.has(m.pending_request) ? answers.get(m.pending_request) : m) };
}

export function mergeBoundReply(sessions, chatId, requestId, userMessage, aiMessage, messageId) {
  return sessions.map((session) => {
    if (String(session.id) !== String(chatId)) return session;
    const match = session.messages.findIndex((message) => message.request_id === requestId && message.sender === 'user');
    if (match < 0) return session;
    const messages = [...session.messages];
    messages[match] = { ...userMessage, id: messageId, request_id: requestId, server_message_id: messageId };
    // Replace only this request's placeholder/result; never overwrite a newer turn.
    const oldAnswer = messages.findIndex((message) => message.reply_to_request_id === requestId);
    const answer = { ...aiMessage, id: `${messageId}:answer`, server_message_id: messageId, reply_to_request_id: requestId };
    if (oldAnswer >= 0) messages[oldAnswer] = answer;
    else messages.splice(match + 1, 0, answer);
    const hasLaterTurn = messages.slice(match + 1).some((message) => message.sender === 'user');
    return { ...session, messages, latest_message_id: hasLaterTurn ? session.latest_message_id : messageId };
  });
}
