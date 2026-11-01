// All asynchronous replies carry the initiating server ID, never the current tab.
export function updateSessionMessages(sessions, sessionId, messages, deletedIds, changes = {}) {
  if (deletedIds.has(sessionId)) return sessions;
  return sessions.map((session) => session.id === sessionId
    ? { ...session, ...changes, messages }
    : session);
}

export function mergeEarlierMessages(earlier, current) {
  const seen = new Set();
  return [...earlier, ...current].filter((message) => {
    if (seen.has(message.id)) return false;
    seen.add(message.id);
    return true;
  });
}

export function hasLegacyChats(storage, currentKey) {
  try {
    const sessions = JSON.parse(storage.getItem(currentKey.replace('_v2_', '_')) || '[]');
    return Array.isArray(sessions) && sessions.some((s) => Array.isArray(s?.messages) && s.messages.length > 1);
  } catch { return false; }
}
