/* eslint-disable react-refresh/only-export-components */
import { createContext, useCallback, useContext, useMemo, useRef, useState } from 'react';

const StaffChatContext = createContext(null);

function readChatIndex(user) {
  if (!user || user.status !== 'active' || user.id == null) return { sessions: [], activeSessionId: null };
  const owner = String(user.id).replace(/[^a-zA-Z0-9_-]/g, '_');
  try {
    const stored = JSON.parse(localStorage.getItem(`jh_ai_chat_sessions_${owner}`) || '[]');
    const sessions = Array.isArray(stored) ? stored.map((item) => ({
      id: item.id,
      title: item.title || 'New Chat',
      updated_at: item.updated_at || '',
    })) : [];
    const activeSessionId = localStorage.getItem(`jh_active_chat_session_${owner}`);
    return { sessions, activeSessionId: activeSessionId ? Number(activeSessionId) : sessions[0]?.id || null };
  } catch {
    return { sessions: [], activeSessionId: null };
  }
}

export function StaffChatProvider({ user, children }) {
  const [chatIndex, setChatIndex] = useState(() => readChatIndex(user));
  const [command, setCommand] = useState(null);
  const commandCount = useRef(0);

  const publish = useCallback((sessions, activeSessionId) => {
    setChatIndex({
      sessions: sessions.map((item) => ({ id: item.id, title: item.title, updated_at: item.updated_at })),
      activeSessionId,
    });
  }, []);

  const request = useCallback((type, sessionId = null) => {
    commandCount.current += 1;
    setCommand({ type, sessionId, id: commandCount.current });
  }, []);

  const acknowledge = useCallback((id) => {
    setCommand((current) => (current?.id === id ? null : current));
  }, []);

  const value = useMemo(() => ({ ...chatIndex, command, publish, request, acknowledge }),
    [chatIndex, command, publish, request, acknowledge]);

  return <StaffChatContext.Provider value={value}>{children}</StaffChatContext.Provider>;
}

export function useStaffChat() {
  return useContext(StaffChatContext);
}
