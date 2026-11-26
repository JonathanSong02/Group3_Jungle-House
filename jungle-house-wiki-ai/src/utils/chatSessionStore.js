// Saved-chat helpers for "AI keeps running after the page is left" (2026-11-26).
//
// A chat reply can now arrive after the staff member left the chat page. React
// state of a closed page no longer updates, so the reply is written straight
// into the saved chats (localStorage) and any open chat page is told to reload.

export function readSavedList(storage, key) {
  try {
    const value = JSON.parse(storage?.getItem(key) ?? 'null');
    return Array.isArray(value) ? value : null;
  } catch {
    return null;
  }
}

// Same rules as before: only that chat changes; a "New Chat" gets the question as its title.
export function withSessionMessages(sessions, sessionId, nextMessages, newTitle, updatedAt) {
  return sessions.map((session) => {
    if (session.id !== sessionId) return session;
    const shouldUpdateTitle = session.title === 'New Chat' && newTitle && String(newTitle).trim();
    return {
      ...session,
      title: shouldUpdateTitle ? newTitle : session.title,
      messages: nextMessages,
      updated_at: updatedAt,
    };
  });
}

function plainAiMessage(text, source) {
  return {
    id: Date.now() + 1,
    sender: 'ai',
    type: 'text',
    text,
    context: { unclear_count: 0 },
    unclear_count: 0,
    escalation_ready: false,
    escalation_required: false,
    confidence: 0,
    confidence_label: 'low',
    source,
    fallback: true,
    fallback_message: text,
    message: text,
  };
}

// A reply collected after a page reload (see aiTaskManager.resume).
export function inboxEntryToMessage(entry, buildMessage, texts) {
  if (entry.failed) return plainAiMessage(texts.unfinished, 'ai_task_unfinished');
  if (entry.ok) return buildMessage(entry.data || {});
  const serverMessage = entry.data?.message;
  const text = (typeof serverMessage === 'string' && serverMessage.trim()) || texts.unavailable;
  return plainAiMessage(text, 'frontend_request_error');
}

const listeners = new Set();

export function subscribeChatStorage(listener) {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

export function notifyChatStorageChanged(key) {
  listeners.forEach((listener) => listener(key));
}
