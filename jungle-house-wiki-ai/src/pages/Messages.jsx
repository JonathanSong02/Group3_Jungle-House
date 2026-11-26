import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import api from '../services/api';
import { useAuth } from '../context/AuthContext';
import { useLanguage } from '../i18n/LanguageContext';
import '../styles/Messages.css';
import { MessageAttachment, MessageAttachmentPicker } from '../components/MessageAttachment';
import { messagePayload, pastedImage, validateMessageFile } from '../utils/messageAttachment';

// UI hint only: the backend independently enforces the five-minute rule using MySQL time.
const MESSAGE_ACTION_WINDOW_MS = 5 * 60 * 1000;

const getInitials = (value = '') => {
  return String(value)
    .trim()
    .split(/\s+/)
    .slice(0, 2)
    .map((part) => part.charAt(0).toUpperCase())
    .join('') || '?';
};

const formatThreadTime = (value, locale = 'en-GB') => {
  if (!value) return '';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return '';

  const now = new Date();
  const sameDay = date.toDateString() === now.toDateString();

  return sameDay
    ? date.toLocaleTimeString(locale, { hour: '2-digit', minute: '2-digit' })
    : date.toLocaleDateString(locale, { day: '2-digit', month: 'short' });
};


const formatMessageTime = (value, locale = 'en-GB') => {
  if (!value) return '';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return '';
  return date.toLocaleTimeString(locale, { hour: '2-digit', minute: '2-digit' });
};

const dayKey = (value) => {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return '';
  return `${date.getFullYear()}-${date.getMonth()}-${date.getDate()}`;
};

const formatDayLabel = (
  value,
  locale = 'en-GB',
  todayLabel = 'Today',
  yesterdayLabel = 'Yesterday'
) => {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return '';

  const now = new Date();
  const yesterday = new Date(now);
  yesterday.setDate(now.getDate() - 1);

  if (dayKey(date) === dayKey(now)) return todayLabel;
  if (dayKey(date) === dayKey(yesterday)) return yesterdayLabel;

  return date.toLocaleDateString(locale, {
    weekday: 'short',
    day: '2-digit',
    month: 'short',
    year: date.getFullYear() === now.getFullYear() ? undefined : 'numeric',
  });
};

const isWithinMessageActionWindow = (createdAt, nowValue = Date.now()) => {
  const createdTime = new Date(createdAt).getTime();

  if (Number.isNaN(createdTime)) return false;

  const elapsed = nowValue - createdTime;
  return elapsed >= 0 && elapsed <= MESSAGE_ACTION_WINDOW_MS;
};

function MoreIcon() {
  return (
    <svg
      className="messages-more-icon"
      viewBox="0 0 24 24"
      aria-hidden="true"
    >
      <circle cx="5" cy="12" r="1.7" fill="currentColor" />
      <circle cx="12" cy="12" r="1.7" fill="currentColor" />
      <circle cx="19" cy="12" r="1.7" fill="currentColor" />
    </svg>
  );
}


function SearchIcon() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <circle cx="11" cy="11" r="6.5" />
      <path d="m16 16 4.5 4.5" />
    </svg>
  );
}

function PlusIcon() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <path d="M12 5v14M5 12h14" />
    </svg>
  );
}

function BackIcon() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <path d="m15 18-6-6 6-6" />
    </svg>
  );
}

function SendIcon() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <path d="M4 4.5 20 12 4 19.5l2.1-6.1L14 12l-7.9-1.4L4 4.5Z" />
    </svg>
  );
}

function ClockIcon() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <circle cx="12" cy="12" r="8" />
      <path d="M12 7v5l3 2" />
    </svg>
  );
}

function CheckIcon({ double = false }) {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      {double ? (
        <>
          <path d="m3.8 12.5 3.4 3.4 6.5-7" />
          <path d="m9.6 12.5 3.4 3.4 7.2-8" />
        </>
      ) : (
        <path d="m5 12.5 4 4 10-10" />
      )}
    </svg>
  );
}

function ErrorIcon() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <circle cx="12" cy="12" r="8" />
      <path d="M12 7.5v6M12 16.8h.01" />
    </svg>
  );
}

export default function Messages() {
  const { user } = useAuth();
  const { t, tOr, locale } = useLanguage();
  const currentUserId = user?.user_id || user?.id;

  const [users, setUsers] = useState([]);
  const [threads, setThreads] = useState([]);
  const [threadMessages, setThreadMessages] = useState([]);
  const [selectedThread, setSelectedThread] = useState(null);

  const [form, setForm] = useState({
    receiver_id: '',
    subject: '',
    message: '',
  });

  const [replyText, setReplyText] = useState('');
  const [editingId, setEditingId] = useState(null);
  const [editingText, setEditingText] = useState('');

  const [loading, setLoading] = useState(true);
  const [threadLoading, setThreadLoading] = useState(false);
  const [sending, setSending] = useState(false);
  const [replyFile, setReplyFile] = useState(null);
  const [newMessageFile, setNewMessageFile] = useState(null);
  const [messageText, setMessageText] = useState('');

  const [threadSearch, setThreadSearch] = useState('');
  const [newChatSearch, setNewChatSearch] = useState('');
  const [showComposer, setShowComposer] = useState(false);
  const [openMenuId, setOpenMenuId] = useState(null);
  const [nowValue, setNowValue] = useState(Date.now());
  const [toast, setToast] = useState(null);
  const toastTimerRef = useRef(null);
  const chatBodyRef = useRef(null);
  const replyInputRef = useRef(null);

  const fetchData = useCallback(async ({ silent = false } = {}) => {
    if (!currentUserId) {
      if (!silent) setLoading(false);
      setMessageText(t('msg.err.noUser'));
      return;
    }

    try {
      if (!silent) setLoading(true);
      if (!silent) setMessageText('');

      const [usersResponse, threadsResponse] = await Promise.all([
        api.get('/messages/users'),
        api.get(`/messages/threads/${currentUserId}`),
      ]);

      setUsers(Array.isArray(usersResponse.data) ? usersResponse.data : []);
      setThreads(Array.isArray(threadsResponse.data) ? threadsResponse.data : []);
    } catch (error) {
      console.error('Fetch messages error:', error);
      if (!silent) setMessageText(error.response?.data?.message || t('msg.err.load'));
    } finally {
      if (!silent) setLoading(false);
    }
  }, [currentUserId, t]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  const showToast = useCallback((message, type = 'error') => {
    if (toastTimerRef.current) window.clearTimeout(toastTimerRef.current);
    setToast({ message, type });
    toastTimerRef.current = window.setTimeout(() => setToast(null), 5200);
  }, []);

  useEffect(() => () => {
    if (toastTimerRef.current) window.clearTimeout(toastTimerRef.current);
  }, []);

  useEffect(() => {
    if (!chatBodyRef.current || threadLoading) return;
    chatBodyRef.current.scrollTo({
      top: chatBodyRef.current.scrollHeight,
      behavior: 'smooth',
    });
  }, [threadMessages, threadLoading]);

  useEffect(() => {
    const timer = window.setInterval(() => {
      setNowValue(Date.now());
    }, 15000);

    return () => window.clearInterval(timer);
  }, []);

  useEffect(() => {
    const closeMenu = (event) => {
      if (!event.target.closest('.messages-message-menu')) {
        setOpenMenuId(null);
      }
    };

    const closeOnEscape = (event) => {
      if (event.key === 'Escape') {
        setOpenMenuId(null);
      }
    };

    document.addEventListener('pointerdown', closeMenu);
    document.addEventListener('keydown', closeOnEscape);

    return () => {
      document.removeEventListener('pointerdown', closeMenu);
      document.removeEventListener('keydown', closeOnEscape);
    };
  }, []);

  const receiverOptions = useMemo(() => {
    return users.filter((item) => Number(item.user_id) !== Number(currentUserId));
  }, [users, currentUserId]);

  const filteredThreads = useMemo(() => {
    const keyword = threadSearch.trim().toLowerCase();

    if (!keyword) return threads;

    return threads.filter((item) => {
      const haystack = [
        item.other_user_name,
        item.subject,
        item.latest_message,
      ]
        .filter(Boolean)
        .join(' ')
        .toLowerCase();

      return haystack.includes(keyword);
    });
  }, [threads, threadSearch]);

  const filteredNewChatUsers = useMemo(() => {
    const keyword = newChatSearch.trim().toLowerCase();

    if (!keyword) return receiverOptions;

    return receiverOptions.filter((item) => {
      const haystack = [item.full_name, item.email, item.role_name]
        .filter(Boolean)
        .join(' ')
        .toLowerCase();

      return haystack.includes(keyword);
    });
  }, [receiverOptions, newChatSearch]);

  const unreadCount = threads.reduce(
    (total, item) => total + Number(item.unread_count || 0),
    0
  );

  const getOtherUserId = (thread) => {
    if (!thread) return null;

    return Number(thread.latest_sender_id) === Number(currentUserId)
      ? Number(thread.latest_receiver_id)
      : Number(thread.latest_sender_id);
  };

  const selectedNewChatUser = receiverOptions.find(
    (item) => Number(item.user_id) === Number(form.receiver_id)
  );

  const handleChange = (event) => {
    const { name, value } = event.target;

    setForm((prev) => ({
      ...prev,
      [name]: value,
    }));
  };

  const selectFile = (file, setter) => {
    if (sending) return;
    if (!validateMessageFile(file)) {
      showToast(tOr('msg.invalidAttachment', 'Choose an image, PDF or Word document under 7MB.'));
      return;
    }
    setter(file);
  };

  const sendMessage = async (event) => {
    event.preventDefault();

    if (sending) return;
    if (!form.receiver_id || (!form.message.trim() && !newMessageFile)) {
      setMessageText(
        tOr(
          'msg.err.receiverMessageRequired',
          'Choose a person and write a message first.'
        )
      );
      return;
    }

    const receiverId = Number(form.receiver_id);
    const receiver = receiverOptions.find(
      (item) => Number(item.user_id) === receiverId
    );
    const subject = form.subject.trim() || 'Direct message';
    const message = form.message.trim();

    try {
      setSending(true);
      setMessageText('');

      const response = await api.post('/messages/send', messagePayload({
        receiver_id: receiverId,
        subject,
        message,
      }, newMessageFile));

      const sentMessage = response.data?.sent_message || {
        message_id: response.data?.message_id,
        thread_id: response.data?.thread_id,
        sender_id: currentUserId,
        receiver_id: receiverId,
        subject,
        message,
        created_at: new Date().toISOString(),
        sender_name: user?.full_name || user?.name || t('msg.you'),
        receiver_name: receiver?.full_name || t('msg.unknownUser'),
        is_read: false,
      };

      const nextThread = {
        thread_id: sentMessage.thread_id,
        subject,
        latest_message: sentMessage.message,
        latest_created_at: sentMessage.created_at,
        latest_sender_id: sentMessage.sender_id,
        latest_receiver_id: sentMessage.receiver_id,
        other_user_name: receiver?.full_name || sentMessage.receiver_name || t('msg.unknownUser'),
        unread_count: 0,
      };

      setThreads((current) => [
        nextThread,
        ...current.filter((item) => Number(item.thread_id) !== Number(nextThread.thread_id)),
      ]);
      setSelectedThread(nextThread);
      setThreadMessages([sentMessage]);
      setForm({ receiver_id: '', subject: '', message: '' });
      setNewMessageFile(null);
      setNewChatSearch('');
      setShowComposer(false);
    } catch (error) {
      console.error('Send message error:', error);
      const fallback = error.request && !error.response
        ? tOr('msg.err.network', 'Message not sent. Check your connection and try again.')
        : error.response?.data?.message || t('msg.err.send');
      showToast(fallback, 'error');
    } finally {
      setSending(false);
    }
  };

  const openThread = async (thread) => {
    if (sending) return;
    try {
      setSelectedThread(thread);
      setThreadLoading(true);
      setMessageText('');
      setReplyText('');
      setReplyFile(null);
      setEditingId(null);
      setEditingText('');
      setOpenMenuId(null);

      const response = await api.get(
        `/messages/thread/${thread.thread_id}/${currentUserId}`
      );
      setThreadMessages(Array.isArray(response.data) ? response.data : []);

      await fetchData({ silent: true });
    } catch (error) {
      console.error('Open thread error:', error);
      setMessageText(
        error.response?.data?.message || t('msg.err.open')
      );
    } finally {
      setThreadLoading(false);
    }
  };


  const syncOpenThread = useCallback(async () => {
    if (!selectedThread?.thread_id || !currentUserId) return;

    try {
      const response = await api.get(
        `/messages/thread/${selectedThread.thread_id}/${currentUserId}`
      );
      const serverMessages = Array.isArray(response.data) ? response.data : [];

      setThreadMessages((current) => {
        const localPending = current.filter(
          (item) =>
            item.client_status === 'sending' ||
            item.client_status === 'failed'
        );

        if (localPending.length === 0) return serverMessages;

        const serverIds = new Set(
          serverMessages.map((item) => String(item.message_id))
        );

        const unmatchedLocal = localPending.filter((localItem) => {
          if (serverIds.has(String(localItem.message_id))) return false;

          return !serverMessages.some((serverItem) => {
            if (
              Number(serverItem.sender_id) !== Number(localItem.sender_id) ||
              String(serverItem.message || '') !== String(localItem.message || '') ||
              (localItem.file && !serverItem.attachments?.some((attachment) =>
                attachment.name === localItem.file.name && attachment.size === localItem.file.size))
            ) {
              return false;
            }

            const serverTime = new Date(serverItem.created_at).getTime();
            const localTime = new Date(localItem.created_at).getTime();

            return (
              Number.isFinite(serverTime) &&
              Number.isFinite(localTime) &&
              Math.abs(serverTime - localTime) <= 30000
            );
          });
        });

        return [...serverMessages, ...unmatchedLocal].sort(
          (a, b) => new Date(a.created_at) - new Date(b.created_at)
        );
      });
    } catch (error) {
      console.debug('Silent message sync skipped:', error?.message);
    }
  }, [selectedThread?.thread_id, currentUserId]);

  useEffect(() => {
    if (!currentUserId) return undefined;

    const sync = () => {
      if (document.visibilityState !== 'visible') return;
      fetchData({ silent: true });
      syncOpenThread();
    };

    const timer = window.setInterval(sync, 5000);
    document.addEventListener('visibilitychange', sync);

    return () => {
      window.clearInterval(timer);
      document.removeEventListener('visibilitychange', sync);
    };
  }, [currentUserId, fetchData, syncOpenThread]);

  const chooseNewChatUser = async (person) => {
    if (sending) return;
    const existingThread = threads.find(
      (thread) => getOtherUserId(thread) === Number(person.user_id)
    );

    if (existingThread) {
      setShowComposer(false);
      setNewChatSearch('');
      setForm({ receiver_id: '', subject: '', message: '' });
      await openThread(existingThread);
      return;
    }

    setForm({
      receiver_id: String(person.user_id),
      subject: 'Direct message',
      message: '',
    });
  };

  const getReplyReceiverId = () => {
    if (!selectedThread || threadMessages.length === 0) return null;

    const lastMessage = threadMessages[threadMessages.length - 1];

    if (Number(lastMessage.sender_id) === Number(currentUserId)) {
      return lastMessage.receiver_id;
    }

    return lastMessage.sender_id;
  };

  const postReplyMessage = async (optimisticMessage) => {
    const optimisticId = optimisticMessage.message_id;

    setThreadMessages((current) =>
      current.map((item) =>
        item.message_id === optimisticId
          ? { ...item, client_status: 'sending' }
          : item
      )
    );

    try {
      setSending(true);

      const response = await api.post('/messages/reply', messagePayload({
        thread_id: optimisticMessage.thread_id,
        parent_message_id: optimisticMessage.parent_message_id || null,
        receiver_id: optimisticMessage.receiver_id,
        subject: optimisticMessage.subject || 'Direct message',
        message: optimisticMessage.message,
      }, optimisticMessage.file));

      const sentMessage = response.data?.sent_message || {
        ...optimisticMessage,
        message_id: response.data?.message_id || optimisticId,
        client_status: undefined,
      };

      setThreadMessages((current) => {
        let replaced = false;
        const next = current.map((item) => {
          if (item.message_id !== optimisticId) return item;
          replaced = true;
          return sentMessage;
        });

        return replaced ? next : [...next, sentMessage];
      });

      setThreads((current) => {
        const updated = current.map((item) =>
          Number(item.thread_id) === Number(optimisticMessage.thread_id)
            ? {
                ...item,
                latest_message: sentMessage.message,
                latest_created_at: sentMessage.created_at,
                latest_sender_id: sentMessage.sender_id,
                latest_receiver_id: sentMessage.receiver_id,
                unread_count: 0,
              }
            : item
        );

        return updated.sort(
          (a, b) =>
            new Date(b.latest_created_at) - new Date(a.latest_created_at)
        );
      });
    } catch (error) {
      console.error('Reply error:', error);

      setThreadMessages((current) =>
        current.map((item) =>
          item.message_id === optimisticId
            ? { ...item, client_status: 'failed' }
            : item
        )
      );

      const fallback =
        error.request && !error.response
          ? tOr(
              'msg.err.network',
              'Message not sent. Check your connection and try again.'
            )
          : error.response?.data?.message || t('msg.err.reply');

      showToast(fallback, 'error');
    } finally {
      setSending(false);
    }
  };

  const sendReply = async (event) => {
    event.preventDefault();

    if (!selectedThread || (!replyText.trim() && !replyFile) || sending) {
      if (!replyText.trim() && !replyFile) setMessageText(t('msg.err.replyFirst'));
      return;
    }

    const receiverId = getReplyReceiverId();

    if (!receiverId) {
      setMessageText(t('msg.err.noReceiver'));
      return;
    }

    const message = replyText.trim();
    const lastPersistedMessage = [...threadMessages]
      .reverse()
      .find((item) => !item.client_status);
    const optimisticId = `local-${Date.now()}-${Math.random()
      .toString(36)
      .slice(2, 8)}`;

    const optimisticMessage = {
      message_id: optimisticId,
      thread_id: selectedThread.thread_id,
      parent_message_id: lastPersistedMessage?.message_id || null,
      sender_id: currentUserId,
      receiver_id: receiverId,
      subject: selectedThread.subject || 'Direct message',
      message,
      file: replyFile,
      is_read: false,
      created_at: new Date().toISOString(),
      edited_at: null,
      sender_name: user?.full_name || user?.name || t('msg.you'),
      receiver_name: selectedThread.other_user_name,
      client_status: 'sending',
    };

    setReplyText('');
    setReplyFile(null);
    setMessageText('');

    if (replyInputRef.current) {
      replyInputRef.current.style.height = '';
    }

    setThreadMessages((current) => [...current, optimisticMessage]);
    await postReplyMessage(optimisticMessage);
  };

  const retryFailedMessage = async (item) => {
    if (sending || item.client_status !== 'failed') return;
    await postReplyMessage({ ...item, client_status: 'sending' });
  };

  const startEdit = (item) => {
    if (!isWithinMessageActionWindow(item.created_at, Date.now())) {
      setMessageText(t('msg.err.editWindow'));
      setOpenMenuId(null);
      return;
    }

    setEditingId(item.message_id);
    setEditingText(item.message);
    setOpenMenuId(null);
  };

  const cancelEdit = () => {
    setEditingId(null);
    setEditingText('');
  };

  const saveEdit = async (messageId) => {
    if (!editingText.trim()) {
      setMessageText(t('msg.err.empty'));
      return;
    }

    try {
      setMessageText('');

      await api.put(`/messages/edit/${messageId}`, {
        user_id: currentUserId,
        message: editingText.trim(),
      });

      const updatedText = editingText.trim();

      setThreadMessages((current) =>
        current.map((item) =>
          Number(item.message_id) === Number(messageId)
            ? {
                ...item,
                message: updatedText,
                edited_at: new Date().toISOString(),
              }
            : item
        )
      );

      setEditingId(null);
      setEditingText('');
      await fetchData({ silent: true });
    } catch (error) {
      console.error('Edit message error:', error);
      setMessageText(
        error.response?.data?.message || t('msg.err.edit')
      );
    }
  };

  const deleteMessageForMe = async (messageId) => {
    const confirmDelete = window.confirm(t('msg.confirm.deleteMe'));

    if (!confirmDelete) return;

    try {
      setMessageText('');
      setOpenMenuId(null);

      await api.put(`/messages/delete/${messageId}`, {
        user_id: currentUserId,
      });

      setThreadMessages((current) =>
        current.filter(
          (item) => Number(item.message_id) !== Number(messageId)
        )
      );

      await fetchData({ silent: true });
    } catch (error) {
      console.error('Delete message error:', error);
      setMessageText(
        error.response?.data?.message || t('msg.err.delete')
      );
    }
  };

  const deleteMessageForEveryone = async (item) => {
    if (!isWithinMessageActionWindow(item.created_at, Date.now())) {
      setMessageText(t('msg.err.deleteWindow'));
      setOpenMenuId(null);
      return;
    }

    if (Number(item.sender_id) !== Number(currentUserId)) {
      setMessageText(t('msg.err.deleteOwn'));
      setOpenMenuId(null);
      return;
    }

    const confirmDelete = window.confirm(t('msg.confirm.deleteEveryone'));

    if (!confirmDelete) return;

    try {
      setMessageText('');
      setOpenMenuId(null);

      // One authenticated request; Flask atomically hides the message for
      // both participants and enforces sender ownership and the 5-minute limit.
      await api.put(`/messages/delete-for-everyone/${item.message_id}`);

      setThreadMessages((current) =>
        current.filter(
          (message) => Number(message.message_id) !== Number(item.message_id)
        )
      );

      await fetchData({ silent: true });
    } catch (error) {
      console.error('Delete for everyone error:', error);
      setMessageText(
        error.response?.data?.message ||
          t('msg.err.deleteEveryone')
      );
    }
  };

  return (
    <div className="messages-page">
      <h1 className="messages-sr-only">{t('msg.title')}</h1>

      {toast ? (
        <div
          className={`messages-toast ${toast.type || 'error'}`}
          role="status"
          aria-live="polite"
        >
          <span className="messages-toast-icon" aria-hidden="true">!</span>
          <span>{toast.message}</span>
          <button
            type="button"
            onClick={() => setToast(null)}
            aria-label={tOr('common.close', 'Close')}
          >
            ×
          </button>
        </div>
      ) : null}

      {messageText ? (
        <div className="messages-global-alert" role="alert">
          {messageText}
        </div>
      ) : null}

      <section
        className={`messages-chat-shell ${selectedThread ? 'has-thread' : ''}`}
      >
        <aside
          className={`messages-sidebar ${showComposer ? 'is-composing' : ''}`}
        >
          <div className="messages-sidebar-top">
            <div className="messages-sidebar-title">
              <h2>
                {showComposer
                  ? tOr('msg.newChat', 'New chat')
                  : tOr('msg.chats', 'Chats')}
              </h2>

              {!showComposer && unreadCount > 0 ? (
                <span
                  className="messages-header-unread"
                  title={t('msg.unreadN', { n: unreadCount })}
                >
                  {unreadCount > 99 ? '99+' : unreadCount}
                </span>
              ) : null}
            </div>

            <button
              type="button"
              className="messages-top-action"
              onClick={() => {
                setShowComposer((current) => !current);
                setMessageText('');
                setNewChatSearch('');
                setForm({ receiver_id: '', subject: '', message: '' });
                setNewMessageFile(null);
              }}
              aria-label={
                showComposer
                  ? tOr('common.back', 'Back')
                  : tOr('msg.newChat', 'New chat')
              }
              title={
                showComposer
                  ? tOr('common.back', 'Back')
                  : tOr('msg.newChat', 'New chat')
              }
            >
              {showComposer ? <BackIcon /> : <PlusIcon />}
            </button>
          </div>

          {showComposer ? (
            <div className="messages-new-chat-panel">
              {!form.receiver_id ? (
                <>
                  <label className="messages-search-box">
                    <SearchIcon />
                    <input
                      type="search"
                      value={newChatSearch}
                      onChange={(event) => setNewChatSearch(event.target.value)}
                      placeholder={tOr('msg.searchPeople', 'Search people')}
                      autoFocus
                    />
                  </label>

                  <div className="messages-new-chat-users">
                    {filteredNewChatUsers.length === 0 ? (
                      <div className="messages-empty-card">
                        {tOr('msg.noPeople', 'No matching people found.')}
                      </div>
                    ) : (
                      filteredNewChatUsers.map((person) => (
                        <button
                          type="button"
                          key={person.user_id}
                          className="messages-person-row"
                          onClick={() => chooseNewChatUser(person)}
                        >
                          <span className="messages-thread-avatar">
                            {getInitials(person.full_name || 'U')}
                          </span>

                          <span className="messages-person-copy">
                            <strong>
                              {person.full_name || t('msg.unknownUser')}
                            </strong>
                            <small>
                              {tOr(
                                `role.${String(person.role_name || 'user')
                                  .toLowerCase()
                                  .replace(/[\s_-]/g, '')}`,
                                person.role_name || 'User'
                              )}
                            </small>
                          </span>
                        </button>
                      ))
                    )}
                  </div>
                </>
              ) : (
                <form
                  className="messages-first-message-form"
                  onSubmit={sendMessage}
                >
                  <button
                    type="button"
                    className="messages-new-recipient"
                    disabled={sending}
                    onClick={() => {
                      setNewMessageFile(null);
                      setForm({
                        receiver_id: '',
                        subject: '',
                        message: '',
                      });
                    }}
                  >
                    <BackIcon />

                    <span className="messages-thread-avatar">
                      {getInitials(selectedNewChatUser?.full_name || 'U')}
                    </span>

                    <span>
                      <strong>
                        {selectedNewChatUser?.full_name ||
                          t('msg.unknownUser')}
                      </strong>
                      <small>
                        {tOr('msg.changeRecipient', 'Choose another person')}
                      </small>
                    </span>
                  </button>

                  <label className="messages-first-message-field">
                    <span>{tOr('msg.firstMessage', 'First message')}</span>
                    <textarea
                      name="message"
                      rows="5"
                      value={form.message}
                      onChange={handleChange}
                      onPaste={(event) => pastedImage(event, (file) => selectFile(file, setNewMessageFile))}
                      placeholder={t('msg.writeMessage')}
                      autoFocus
                    />
                  </label>

                  <MessageAttachmentPicker file={newMessageFile} onSelect={(file) => selectFile(file, setNewMessageFile)}
                    onRemove={() => setNewMessageFile(null)} disabled={sending} />
                  <button
                    type="submit"
                    className="messages-send-new-btn"
                    disabled={sending || (!form.message.trim() && !newMessageFile)}
                  >
                    <SendIcon />
                    <span>
                      {sending
                        ? t('msg.sending')
                        : tOr('msg.startChat', 'Start chat')}
                    </span>
                  </button>
                </form>
              )}
            </div>
          ) : (
            <>
              <div className="messages-search-wrap">
                <label className="messages-search-box">
                  <SearchIcon />
                  <input
                    type="search"
                    value={threadSearch}
                    onChange={(event) => setThreadSearch(event.target.value)}
                    placeholder={t('msg.searchChats')}
                  />
                </label>
              </div>

              <div className="messages-thread-list">
                {loading ? (
                  <div className="messages-empty-card">
                    {t('msg.loadingConv')}
                  </div>
                ) : filteredThreads.length === 0 ? (
                  <div className="messages-empty-card">{t('msg.noConv')}</div>
                ) : (
                  filteredThreads.map((thread) => {
                    const isActive =
                      Number(selectedThread?.thread_id) ===
                      Number(thread.thread_id);
                    const isUnread =
                      Number(thread.unread_count || 0) > 0;
                    const latestIsMine =
                      Number(thread.latest_sender_id) ===
                      Number(currentUserId);

                    return (
                      <button
                        key={thread.thread_id}
                        type="button"
                        className={`messages-thread-item ${
                          isActive ? 'active' : ''
                        } ${isUnread ? 'unread' : ''}`}
                        onClick={() => openThread(thread)}
                      >
                        <span className="messages-thread-avatar">
                          {getInitials(thread.other_user_name || 'U')}
                        </span>

                        <span className="messages-thread-content">
                          <span className="messages-thread-row">
                            <strong>
                              {thread.other_user_name || t('msg.unknown')}
                            </strong>
                            <time className="messages-thread-time">
                              {formatThreadTime(
                                thread.latest_created_at,
                                locale
                              )}
                            </time>
                          </span>

                          <span className="messages-thread-preview-row">
                            <span className="messages-thread-preview">
                              {latestIsMine ? `${t('msg.you')}: ` : ''}
                              {thread.latest_message || t('chat.attachFile')}
                            </span>

                            {isUnread ? (
                              <span className="messages-thread-badge">
                                {Number(thread.unread_count) > 99
                                  ? '99+'
                                  : thread.unread_count}
                              </span>
                            ) : null}
                          </span>
                        </span>
                      </button>
                    );
                  })
                )}
              </div>
            </>
          )}
        </aside>

        <section className="messages-chat-main">
          {!selectedThread ? (
            <div className="messages-chat-empty">
              <div className="messages-chat-empty-icon" aria-hidden="true">
                ✦
              </div>
              <h3>
                {tOr('msg.privateMessaging', 'Jungle House Messages')}
              </h3>
              <p>
                {tOr(
                  'msg.privateMessagingHint',
                  'Select a chat to start messaging your team.'
                )}
              </p>
            </div>
          ) : (
            <>
              <header className="messages-chat-header">
                <button
                  type="button"
                  className="messages-mobile-back"
                  onClick={() => {
                    setSelectedThread(null);
                    setThreadMessages([]);
                    setMessageText('');
                  }}
                  aria-label={tOr('common.back', 'Back')}
                >
                  <BackIcon />
                </button>

                <div className="messages-chat-person">
                  <div className="messages-chat-avatar">
                    {getInitials(
                      selectedThread.other_user_name || 'U'
                    )}
                  </div>

                  <div>
                    <h3>
                      {selectedThread.other_user_name ||
                        t('msg.unknownUser')}
                    </h3>
                    <p>
                      {tOr(
                        'msg.internalConversation',
                        'Internal conversation'
                      )}
                    </p>
                  </div>
                </div>

                <div className="messages-chat-header-status">
                  <span
                    className="messages-sync-dot"
                    aria-hidden="true"
                  />
                  <span>{tOr('msg.autoSync', 'Auto-sync')}</span>
                </div>
              </header>

              <div className="messages-chat-body" ref={chatBodyRef}>
                {threadLoading ? (
                  <div className="messages-inline-empty">
                    <span
                      className="messages-loading-spinner"
                      aria-hidden="true"
                    />
                    {t('msg.loadingThread')}
                  </div>
                ) : threadMessages.length === 0 ? (
                  <div className="messages-inline-empty">
                    {t('msg.noMessages')}
                  </div>
                ) : (
                  threadMessages.map((item, index) => {
                    const isMine =
                      Number(item.sender_id) === Number(currentUserId);
                    const withinFiveMinutes =
                      isMine &&
                      !item.client_status &&
                      isWithinMessageActionWindow(
                        item.created_at,
                        nowValue
                      );
                    const previousItem = threadMessages[index - 1];
                    const showDay =
                      index === 0 ||
                      dayKey(previousItem?.created_at) !==
                        dayKey(item.created_at);

                    return (
                      <div
                        className="messages-message-stack"
                        key={item.message_id}
                      >
                        {showDay ? (
                          <div className="messages-day-separator">
                            <span>
                              {formatDayLabel(
                                item.created_at,
                                locale,
                                tOr('common.today', 'Today'),
                                tOr(
                                  'common.yesterday',
                                  'Yesterday'
                                )
                              )}
                            </span>
                          </div>
                        ) : null}

                        <div
                          className={`messages-bubble-row ${
                            isMine ? 'mine' : ''
                          }`}
                        >
                          <div
                            className={`messages-bubble ${
                              isMine ? 'mine' : 'other'
                            } ${item.client_status || ''}`}
                          >
                            {!item.client_status ? (
                              <div className="messages-message-menu">
                                <button
                                  type="button"
                                  className="messages-message-menu-trigger"
                                  onClick={(event) => {
                                    event.stopPropagation();
                                    setOpenMenuId((prev) =>
                                      prev === item.message_id
                                        ? null
                                        : item.message_id
                                    );
                                  }}
                                  aria-label={t('msg.actions')}
                                  aria-expanded={
                                    openMenuId === item.message_id
                                  }
                                >
                                  <MoreIcon />
                                </button>

                                {openMenuId === item.message_id ? (
                                  <div
                                    className={`messages-message-menu-popover ${
                                      isMine
                                        ? 'align-right'
                                        : 'align-left'
                                    }`}
                                  >
                                    {withinFiveMinutes ? (
                                      <button
                                        type="button"
                                        onClick={() => startEdit(item)}
                                      >
                                        <span className="messages-menu-icon">
                                          ✎
                                        </span>
                                        {t('msg.edit')}
                                      </button>
                                    ) : null}

                                    {withinFiveMinutes ? (
                                      <button
                                        type="button"
                                        className="danger"
                                        onClick={() =>
                                          deleteMessageForEveryone(
                                            item
                                          )
                                        }
                                      >
                                        <span className="messages-menu-icon">
                                          ⌫
                                        </span>
                                        {t('msg.deleteEveryone')}
                                      </button>
                                    ) : null}

                                    <button
                                      type="button"
                                      className="danger"
                                      onClick={() =>
                                        deleteMessageForMe(
                                          item.message_id
                                        )
                                      }
                                    >
                                      <span className="messages-menu-icon">
                                        🗑
                                      </span>
                                      {t('msg.deleteMe')}
                                    </button>
                                  </div>
                                ) : null}
                              </div>
                            ) : null}

                            {item.file && <MessageAttachment file={item.file} />}
                            {item.attachments?.map((attachment) => <MessageAttachment key={attachment.attachment_id} attachment={attachment} />)}
                            {editingId === item.message_id ? (
                              <div className="messages-edit-box">
                                <textarea
                                  rows="3"
                                  value={editingText}
                                  onChange={(event) =>
                                    setEditingText(event.target.value)
                                  }
                                />

                                <div className="messages-bubble-actions">
                                  <button
                                    type="button"
                                    className="messages-primary-pill small"
                                    onClick={() =>
                                      saveEdit(item.message_id)
                                    }
                                  >
                                    {t('msg.save')}
                                  </button>

                                  <button
                                    type="button"
                                    className="messages-light-btn small"
                                    onClick={cancelEdit}
                                  >
                                    {t('msg.cancel')}
                                  </button>
                                </div>
                              </div>
                            ) : (
                              <p>{item.message}</p>
                            )}

                            <div className="messages-bubble-footer">
                              {item.edited_at ? (
                                <span className="messages-edited-tag">
                                  {t('msg.edited')}
                                </span>
                              ) : null}

                              <time>
                                {formatMessageTime(
                                  item.created_at,
                                  locale
                                )}
                              </time>

                              {isMine ? (
                                <span
                                  className={`messages-delivery-status ${
                                    item.client_status === 'failed'
                                      ? 'failed'
                                      : item.is_read
                                        ? 'read'
                                        : ''
                                  }`}
                                >
                                  {item.client_status === 'sending' ? (
                                    <span
                                      title={tOr(
                                        'msg.sendingStatus',
                                        'Sending'
                                      )}
                                    >
                                      <ClockIcon />
                                    </span>
                                  ) : item.client_status ===
                                    'failed' ? (
                                    <button
                                      type="button"
                                      onClick={() =>
                                        retryFailedMessage(item)
                                      }
                                      title={tOr(
                                        'msg.retrySend',
                                        'Retry sending'
                                      )}
                                      aria-label={tOr(
                                        'msg.retrySend',
                                        'Retry sending'
                                      )}
                                    >
                                      <ErrorIcon />
                                    </button>
                                  ) : item.is_read ? (
                                    <span
                                      title={tOr(
                                        'msg.readStatus',
                                        'Read'
                                      )}
                                    >
                                      <CheckIcon double />
                                    </span>
                                  ) : (
                                    <span
                                      title={tOr(
                                        'msg.sentStatus',
                                        'Sent'
                                      )}
                                    >
                                      <CheckIcon />
                                    </span>
                                  )}
                                </span>
                              ) : null}
                            </div>
                          </div>
                        </div>
                      </div>
                    );
                  })
                )}
              </div>

              <form
                className="messages-reply-bar"
                onSubmit={sendReply}
              >
                <MessageAttachmentPicker file={replyFile} onSelect={(file) => selectFile(file, setReplyFile)}
                  onRemove={() => setReplyFile(null)} disabled={sending} />
                <textarea
                  ref={replyInputRef}
                  rows="1"
                  value={replyText}
                  onPaste={(event) => pastedImage(event, (file) => selectFile(file, setReplyFile))}
                  onChange={(event) => {
                    setReplyText(event.target.value);
                    event.target.style.height = 'auto';
                    event.target.style.height = `${Math.min(
                      event.target.scrollHeight,
                      120
                    )}px`;
                  }}
                  onKeyDown={(event) => {
                    if (
                      event.key === 'Enter' &&
                      !event.shiftKey &&
                      !event.nativeEvent.isComposing
                    ) {
                      event.preventDefault();
                      event.currentTarget.form?.requestSubmit();
                    }
                  }}
                  placeholder={t('msg.writeReply')}
                  aria-label={t('msg.writeReply')}
                />

                <button
                  type="submit"
                  className="messages-reply-send"
                  disabled={sending || (!replyText.trim() && !replyFile)}
                  aria-label={
                    sending ? t('msg.sending') : t('msg.send')
                  }
                  title={sending ? t('msg.sending') : t('msg.send')}
                >
                  <SendIcon />
                </button>
              </form>
            </>
          )}
        </section>
      </section>
    </div>
  );
}
