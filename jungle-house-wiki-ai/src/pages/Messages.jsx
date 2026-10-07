import { useCallback, useEffect, useMemo, useState } from 'react';
import PageHeader from '../components/PageHeader';
import api from '../services/api';
import { useAuth } from '../context/AuthContext';
import { useLanguage } from '../i18n/LanguageContext';
import '../styles/Messages.css';

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

const isWithinMessageActionWindow = (createdAt, nowValue = Date.now()) => {
  const createdTime = new Date(createdAt).getTime();

  if (Number.isNaN(createdTime)) return false;

  const elapsed = nowValue - createdTime;
  return elapsed >= 0 && elapsed <= MESSAGE_ACTION_WINDOW_MS;
};

function RefreshIcon() {
  return (
    <svg
      className="messages-action-icon"
      viewBox="0 0 24 24"
      aria-hidden="true"
    >
      <path
        d="M20 6v5h-5M4 18v-5h5M18.5 9A7 7 0 0 0 6.7 6.7L4 9M5.5 15A7 7 0 0 0 17.3 17.3L20 15"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.9"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

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

export default function Messages() {
  const { user } = useAuth();
  const { t, tOr, locale } = useLanguage();
  const currentUserId = user?.user_id || user?.id;

  const [users, setUsers] = useState([]);
  const [threads, setThreads] = useState([]);
  const [threadMessages, setThreadMessages] = useState([]);
  const [selectedThread, setSelectedThread] = useState(null);
  const [activeTab, setActiveTab] = useState('inbox');

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
  const [messageText, setMessageText] = useState('');

  const [threadSearch, setThreadSearch] = useState('');
  const [showComposer, setShowComposer] = useState(false);
  const [openMenuId, setOpenMenuId] = useState(null);
  const [nowValue, setNowValue] = useState(Date.now());

  const fetchData = useCallback(async () => {
    if (!currentUserId) {
      setLoading(false);
      setMessageText(t('msg.err.noUser'));
      return;
    }

    try {
      setLoading(true);
      setMessageText('');

      const [usersResponse, threadsResponse] = await Promise.all([
        api.get('/messages/users'),
        api.get(`/messages/threads/${currentUserId}`),
      ]);

      setUsers(Array.isArray(usersResponse.data) ? usersResponse.data : []);
      setThreads(Array.isArray(threadsResponse.data) ? threadsResponse.data : []);
    } catch (error) {
      console.error('Fetch messages error:', error);
      setMessageText(error.response?.data?.message || t('msg.err.load'));
    } finally {
      setLoading(false);
    }
  }, [currentUserId, t]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

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

  const inboxThreads = useMemo(() => {
    return threads.filter(
      (item) =>
        Number(item.latest_sender_id) !== Number(currentUserId) ||
        item.unread_count > 0
    );
  }, [threads, currentUserId]);

  const sentThreads = useMemo(() => {
    return threads.filter(
      (item) => Number(item.latest_sender_id) === Number(currentUserId)
    );
  }, [threads, currentUserId]);

  const filteredByTab = activeTab === 'inbox' ? inboxThreads : sentThreads;

  const filteredThreads = useMemo(() => {
    const keyword = threadSearch.trim().toLowerCase();

    if (!keyword) return filteredByTab;

    return filteredByTab.filter((item) => {
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
  }, [filteredByTab, threadSearch]);

  const unreadCount = threads.reduce(
    (total, item) => total + Number(item.unread_count || 0),
    0
  );

  const handleChange = (event) => {
    const { name, value } = event.target;

    setForm((prev) => ({
      ...prev,
      [name]: value,
    }));
  };

  const sendMessage = async (event) => {
    event.preventDefault();

    if (!form.receiver_id || !form.subject.trim() || !form.message.trim()) {
      setMessageText(t('msg.err.fillAll'));
      return;
    }

    try {
      setSending(true);
      setMessageText('');

      await api.post('/messages/send', {
        sender_id: currentUserId,
        receiver_id: Number(form.receiver_id),
        subject: form.subject.trim(),
        message: form.message.trim(),
      });

      setForm({
        receiver_id: '',
        subject: '',
        message: '',
      });

      setShowComposer(false);
      setMessageText(t('msg.sentOk'));
      setActiveTab('sent');
      await fetchData();
    } catch (error) {
      console.error('Send message error:', error);
      setMessageText(error.response?.data?.message || t('msg.err.send'));
    } finally {
      setSending(false);
    }
  };

  const openThread = async (thread) => {
    try {
      setSelectedThread(thread);
      setThreadLoading(true);
      setMessageText('');
      setReplyText('');
      setEditingId(null);
      setEditingText('');
      setOpenMenuId(null);

      const response = await api.get(
        `/messages/thread/${thread.thread_id}/${currentUserId}`
      );
      setThreadMessages(Array.isArray(response.data) ? response.data : []);

      await fetchData();
    } catch (error) {
      console.error('Open thread error:', error);
      setMessageText(
        error.response?.data?.message || t('msg.err.open')
      );
    } finally {
      setThreadLoading(false);
    }
  };

  const getReplyReceiverId = () => {
    if (!selectedThread || threadMessages.length === 0) return null;

    const lastMessage = threadMessages[threadMessages.length - 1];

    if (Number(lastMessage.sender_id) === Number(currentUserId)) {
      return lastMessage.receiver_id;
    }

    return lastMessage.sender_id;
  };

  const sendReply = async (event) => {
    event.preventDefault();

    if (!selectedThread || !replyText.trim()) {
      setMessageText(t('msg.err.replyFirst'));
      return;
    }

    const receiverId = getReplyReceiverId();

    if (!receiverId) {
      setMessageText(t('msg.err.noReceiver'));
      return;
    }

    try {
      setSending(true);
      setMessageText('');

      const lastMessage = threadMessages[threadMessages.length - 1];

      await api.post('/messages/reply', {
        thread_id: selectedThread.thread_id,
        parent_message_id: lastMessage?.message_id || null,
        sender_id: currentUserId,
        receiver_id: receiverId,
        subject: selectedThread.subject,
        message: replyText.trim(),
      });

      setReplyText('');
      await openThread(selectedThread);
    } catch (error) {
      console.error('Reply error:', error);
      setMessageText(error.response?.data?.message || t('msg.err.reply'));
    } finally {
      setSending(false);
    }
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

      setEditingId(null);
      setEditingText('');

      if (selectedThread) {
        await openThread(selectedThread);
      }
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

      if (selectedThread) {
        await openThread(selectedThread);
      }

      await fetchData();
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

      if (selectedThread) {
        await openThread(selectedThread);
      }

      await fetchData();
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
      <PageHeader
        title={t('msg.title')}
        subtitle={t('msg.subtitle')}
      />

      {messageText && (
        <div className="messages-global-alert">
          {messageText}
        </div>
      )}

      <section className="messages-chat-shell">
        <aside className="messages-sidebar">
          <div className="messages-sidebar-top">
            <div>
              <p className="messages-overline">{t('msg.overline')}</p>
              <h3>{t('msg.conversations')}</h3>
            </div>

            <div className="messages-sidebar-actions">
              <button
                type="button"
                className="messages-icon-btn"
                onClick={fetchData}
                title={t('msg.refreshConv')}
                aria-label={t('msg.refreshConv')}
              >
                <RefreshIcon />
              </button>

              <button
                type="button"
                className="messages-primary-pill"
                onClick={() => setShowComposer((prev) => !prev)}
              >
                {showComposer ? t('common.close') : t('msg.new')}
              </button>
            </div>
          </div>

          <div className="messages-search-wrap">
            <input
              type="text"
              value={threadSearch}
              onChange={(event) => setThreadSearch(event.target.value)}
              placeholder={t('msg.searchChats')}
            />
          </div>

          <div className="messages-tabbar">
            <button
              type="button"
              className={activeTab === 'inbox' ? 'active' : ''}
              onClick={() => setActiveTab('inbox')}
            >
              {t('msg.inbox')}
              {inboxThreads.length > 0 && <span>{inboxThreads.length}</span>}
            </button>

            <button
              type="button"
              className={activeTab === 'sent' ? 'active' : ''}
              onClick={() => setActiveTab('sent')}
            >
              {t('msg.sent')}
              {sentThreads.length > 0 && <span>{sentThreads.length}</span>}
            </button>
          </div>

          {showComposer && (
            <form className="messages-composer-card" onSubmit={sendMessage}>
              <div className="messages-form-grid">
                <label>
                  <span>{t('msg.receiver')}</span>
                  <select
                    name="receiver_id"
                    value={form.receiver_id}
                    onChange={handleChange}
                  >
                    <option value="">{t('msg.selectReceiver')}</option>
                    {receiverOptions.map((item) => (
                      <option key={item.user_id} value={item.user_id}>
                        {item.full_name} ({tOr(`role.${String(item.role_name || 'user').toLowerCase().replace(/[\s_-]/g, '')}`, item.role_name || 'User')})
                      </option>
                    ))}
                  </select>
                </label>

                <label>
                  <span>{t('msg.subject')}</span>
                  <input
                    name="subject"
                    value={form.subject}
                    onChange={handleChange}
                    placeholder={t('msg.subject')}
                  />
                </label>

                <label className="messages-full-width">
                  <span>{t('msg.message')}</span>
                  <textarea
                    name="message"
                    rows="4"
                    value={form.message}
                    onChange={handleChange}
                    placeholder={t('msg.writeMessage')}
                  />
                </label>
              </div>

              <button
                type="submit"
                className="messages-send-new-btn"
                disabled={sending}
              >
                {sending ? t('msg.sending') : t('msg.send')}
              </button>
            </form>
          )}

          <div className="messages-thread-list">
            {loading ? (
              <div className="messages-empty-card">{t('msg.loadingConv')}</div>
            ) : filteredThreads.length === 0 ? (
              <div className="messages-empty-card">
                {t('msg.noConv')}
              </div>
            ) : (
              filteredThreads.map((thread) => {
                const isActive =
                  selectedThread?.thread_id === thread.thread_id;
                const isUnread = Number(thread.unread_count || 0) > 0;

                return (
                  <button
                    key={thread.thread_id}
                    type="button"
                    className={`messages-thread-item ${
                      isActive ? 'active' : ''
                    } ${isUnread ? 'unread' : ''}`}
                    onClick={() => openThread(thread)}
                  >
                    <div className="messages-thread-avatar">
                      {getInitials(thread.other_user_name || 'U')}
                    </div>

                    <div className="messages-thread-content">
                      <div className="messages-thread-row">
                        <h4>{thread.other_user_name || t('msg.unknown')}</h4>
                        <span className="messages-thread-time">
                          {formatThreadTime(thread.latest_created_at, locale)}
                        </span>
                      </div>

                      <p className="messages-thread-subject">
                        {thread.subject}
                      </p>
                      <p className="messages-thread-preview">
                        {thread.latest_message}
                      </p>
                    </div>

                    {isUnread && (
                      <span className="messages-thread-badge">
                        {thread.unread_count}
                      </span>
                    )}
                  </button>
                );
              })
            )}
          </div>

          <div className="messages-sidebar-footer">
            <span>{t('msg.unreadN', { n: unreadCount })}</span>
            <span>{t('msg.totalN', { n: threads.length })}</span>
          </div>
        </aside>

        <section className="messages-chat-main">
          {!selectedThread ? (
            <div className="messages-chat-empty">
              <div className="messages-chat-empty-icon">✉</div>
              <h3>{t('msg.selectConv')}</h3>
              <p>{t('msg.selectConvHint')}</p>
            </div>
          ) : (
            <>
              <header className="messages-chat-header">
                <div className="messages-chat-person">
                  <div className="messages-chat-avatar">
                    {getInitials(selectedThread.other_user_name || 'U')}
                  </div>

                  <div>
                    <h3>
                      {selectedThread.other_user_name || t('msg.unknownUser')}
                    </h3>
                    <p>{selectedThread.subject}</p>
                  </div>
                </div>

                <button
                  type="button"
                  className="messages-light-btn messages-header-refresh"
                  onClick={() => openThread(selectedThread)}
                >
                  <RefreshIcon />
                  <span>{t('msg.refresh')}</span>
                </button>
              </header>

              <div className="messages-chat-body">
                {threadLoading ? (
                  <div className="messages-inline-empty">
                    {t('msg.loadingThread')}
                  </div>
                ) : threadMessages.length === 0 ? (
                  <div className="messages-inline-empty">
                    {t('msg.noMessages')}
                  </div>
                ) : (
                  threadMessages.map((item) => {
                    const isMine =
                      Number(item.sender_id) === Number(currentUserId);
                    const withinFiveMinutes =
                      isMine &&
                      isWithinMessageActionWindow(item.created_at, nowValue);

                    return (
                      <div
                        key={item.message_id}
                        className={`messages-bubble-row ${
                          isMine ? 'mine' : ''
                        }`}
                      >
                        {!isMine && (
                          <div className="messages-bubble-avatar">
                            {getInitials(item.sender_name || 'U')}
                          </div>
                        )}

                        <div
                          className={`messages-bubble ${
                            isMine ? 'mine' : 'other'
                          }`}
                        >
                          <div className="messages-bubble-meta">
                            <strong>
                              {isMine ? t('msg.you') : item.sender_name}
                            </strong>

                            <div className="messages-bubble-meta-right">
                              <span>
                                {new Date(
                                  item.created_at
                                ).toLocaleString(locale)}
                              </span>

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

                                {openMenuId === item.message_id && (
                                  <div
                                    className={`messages-message-menu-popover ${
                                      isMine ? 'align-right' : 'align-left'
                                    }`}
                                  >
                                    {withinFiveMinutes && (
                                      <button
                                        type="button"
                                        onClick={() => startEdit(item)}
                                      >
                                        <span className="messages-menu-icon">
                                          ✎
                                        </span>
                                        {t('msg.edit')}
                                      </button>
                                    )}

                                    {withinFiveMinutes && (
                                      <button
                                        type="button"
                                        className="danger"
                                        onClick={() =>
                                          deleteMessageForEveryone(item)
                                        }
                                      >
                                        <span className="messages-menu-icon">
                                          ⌫
                                        </span>
                                        {t('msg.deleteEveryone')}
                                      </button>
                                    )}

                                    <button
                                      type="button"
                                      className="danger"
                                      onClick={() =>
                                        deleteMessageForMe(item.message_id)
                                      }
                                    >
                                      <span className="messages-menu-icon">
                                        🗑
                                      </span>
                                      {t('msg.deleteMe')}
                                    </button>
                                  </div>
                                )}
                              </div>
                            </div>
                          </div>

                          {editingId === item.message_id ? (
                            <div className="messages-edit-box">
                              <textarea
                                rows="4"
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

                          {item.edited_at && (
                            <small className="messages-edited-tag">
                              {t('msg.edited')}
                            </small>
                          )}
                        </div>
                      </div>
                    );
                  })
                )}
              </div>

              <form className="messages-reply-bar" onSubmit={sendReply}>
                <textarea
                  rows="2"
                  value={replyText}
                  onChange={(event) => setReplyText(event.target.value)}
                  placeholder={t('msg.writeReply')}
                />

                <button
                  type="submit"
                  className="messages-reply-send"
                  disabled={sending}
                >
                  {sending ? t('msg.sending') : t('msg.send')}
                </button>
              </form>
            </>
          )}
        </section>
      </section>
    </div>
  );
}
