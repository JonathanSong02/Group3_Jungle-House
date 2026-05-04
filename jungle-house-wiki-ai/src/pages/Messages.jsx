import { useEffect, useMemo, useState } from 'react';
import PageHeader from '../components/PageHeader';
import api from '../services/api';
import { useAuth } from '../context/AuthContext';

export default function Messages() {
  const { user } = useAuth();
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

  const fetchData = async () => {
    if (!currentUserId) {
      setLoading(false);
      setMessageText('Unable to load messages because user ID is missing.');
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
      setMessageText(error.response?.data?.message || 'Failed to load messages.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchData();
  }, [currentUserId]);

  const receiverOptions = useMemo(() => {
    return users.filter((item) => Number(item.user_id) !== Number(currentUserId));
  }, [users, currentUserId]);

  const inboxThreads = useMemo(() => {
    return threads.filter((item) => Number(item.latest_sender_id) !== Number(currentUserId) || item.unread_count > 0);
  }, [threads, currentUserId]);

  const sentThreads = useMemo(() => {
    return threads.filter((item) => Number(item.latest_sender_id) === Number(currentUserId));
  }, [threads, currentUserId]);

  const filteredThreads = activeTab === 'inbox' ? inboxThreads : sentThreads;

  const unreadCount = threads.reduce((total, item) => total + Number(item.unread_count || 0), 0);

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
      setMessageText('Please select a receiver and fill in the subject and message.');
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

      setMessageText('Message sent successfully.');
      setActiveTab('sent');
      await fetchData();
    } catch (error) {
      console.error('Send message error:', error);
      setMessageText(error.response?.data?.message || 'Failed to send message.');
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

      const response = await api.get(`/messages/thread/${thread.thread_id}/${currentUserId}`);
      setThreadMessages(Array.isArray(response.data) ? response.data : []);

      await fetchData();
    } catch (error) {
      console.error('Open thread error:', error);
      setMessageText(error.response?.data?.message || 'Failed to open conversation.');
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
      setMessageText('Please write a reply first.');
      return;
    }

    const receiverId = getReplyReceiverId();

    if (!receiverId) {
      setMessageText('Unable to identify receiver.');
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
      setMessageText(error.response?.data?.message || 'Failed to send reply.');
    } finally {
      setSending(false);
    }
  };

  const startEdit = (item) => {
    setEditingId(item.message_id);
    setEditingText(item.message);
  };

  const cancelEdit = () => {
    setEditingId(null);
    setEditingText('');
  };

  const saveEdit = async (messageId) => {
    if (!editingText.trim()) {
      setMessageText('Message cannot be empty.');
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
      setMessageText(error.response?.data?.message || 'Failed to edit message.');
    }
  };

  const deleteMessage = async (messageId) => {
    const confirmDelete = window.confirm('Delete this message from your view?');

    if (!confirmDelete) return;

    try {
      setMessageText('');

      await api.put(`/messages/delete/${messageId}`, {
        user_id: currentUserId,
      });

      if (selectedThread) {
        await openThread(selectedThread);
      }

      await fetchData();
    } catch (error) {
      console.error('Delete message error:', error);
      setMessageText(error.response?.data?.message || 'Failed to delete message.');
    }
  };

  return (
    <div>
      <PageHeader
        title="Messages"
        subtitle="Communicate with managers, team leads, and staff directly inside the system."
      />

      <section className="messages-inbox-layout top-gap-sm">
        <aside className="card-like message-compose-card">
          <h3>New Message</h3>
          <p className="muted">Start a new conversation with a registered user.</p>

          <form className="form-stack top-gap" onSubmit={sendMessage}>
            <label>
              Receiver
              <select
                name="receiver_id"
                value={form.receiver_id}
                onChange={handleChange}
              >
                <option value="">Select receiver</option>
                {receiverOptions.map((item) => (
                  <option key={item.user_id} value={item.user_id}>
                    {item.full_name} ({item.role_name || 'User'})
                  </option>
                ))}
              </select>
            </label>

            <label>
              Subject
              <input
                name="subject"
                value={form.subject}
                onChange={handleChange}
                placeholder="Enter message subject"
              />
            </label>

            <label>
              Message
              <textarea
                name="message"
                rows="6"
                value={form.message}
                onChange={handleChange}
                placeholder="Write your message here"
              />
            </label>

            <button type="submit" className="primary-btn" disabled={sending}>
              {sending ? 'Sending...' : 'Send Message'}
            </button>
          </form>
        </aside>

        <section className="card-like message-thread-list-card">
          <div className="row-between wrap-gap">
            <div>
              <h3>Inbox</h3>
              <p className="muted">
                {unreadCount} unread message{unreadCount === 1 ? '' : 's'}.
              </p>
            </div>

            <button type="button" className="secondary-btn" onClick={fetchData}>
              Refresh
            </button>
          </div>

          <div className="message-tab-row top-gap">
            <button
              type="button"
              className={activeTab === 'inbox' ? 'primary-btn' : 'secondary-btn'}
              onClick={() => setActiveTab('inbox')}
            >
              Inbox ({inboxThreads.length})
            </button>

            <button
              type="button"
              className={activeTab === 'sent' ? 'primary-btn' : 'secondary-btn'}
              onClick={() => setActiveTab('sent')}
            >
              Sent ({sentThreads.length})
            </button>
          </div>

          {loading ? (
            <p className="muted top-gap">Loading conversations...</p>
          ) : filteredThreads.length === 0 ? (
            <div className="empty-state-card top-gap">
              <h3>No conversations</h3>
              <p className="muted">
                {activeTab === 'inbox'
                  ? 'Messages sent to you will appear here.'
                  : 'Messages you sent will appear here.'}
              </p>
            </div>
          ) : (
            <div className="message-thread-list top-gap-sm">
              {filteredThreads.map((thread) => (
                <button
                  key={thread.thread_id}
                  type="button"
                  className={
                    selectedThread?.thread_id === thread.thread_id
                      ? 'message-thread-item active'
                      : thread.unread_count > 0
                        ? 'message-thread-item unread'
                        : 'message-thread-item'
                  }
                  onClick={() => openThread(thread)}
                >
                  <div>
                    <p className="message-list-meta">
                      {activeTab === 'sent'
                        ? `To ${thread.other_user_name || 'Unknown'}`
                        : `From ${thread.other_user_name || 'Unknown'}`}
                    </p>

                    <h4>{thread.subject}</h4>

                    <p className="muted small">
                      {thread.latest_message}
                    </p>

                    <p className="muted small">
                      {new Date(thread.latest_created_at).toLocaleString()}
                    </p>
                  </div>

                  {thread.unread_count > 0 && (
                    <span className="status-badge pending">
                      {thread.unread_count}
                    </span>
                  )}
                </button>
              ))}
            </div>
          )}
        </section>

        <section className="card-like message-conversation-card">
          {!selectedThread ? (
            <div className="message-empty-thread">
              <h3>Select a conversation</h3>
              <p className="muted">
                Choose a message thread from the inbox to view and reply.
              </p>
            </div>
          ) : (
            <>
              <div className="row-between wrap-gap">
                <div>
                  <p className="eyebrow">Conversation</p>
                  <h3>{selectedThread.subject}</h3>
                  <p className="muted small">
                    With {selectedThread.other_user_name || 'Unknown User'}
                  </p>
                </div>
              </div>

              {messageText && (
                <div className="card-like top-gap-sm">
                  <p className="muted">{messageText}</p>
                </div>
              )}

              {threadLoading ? (
                <p className="muted top-gap">Loading conversation...</p>
              ) : (
                <div className="message-bubble-list top-gap">
                  {threadMessages.map((item) => {
                    const isMine = Number(item.sender_id) === Number(currentUserId);

                    return (
                      <div
                        key={item.message_id}
                        className={isMine ? 'message-bubble-row mine' : 'message-bubble-row'}
                      >
                        <div className={isMine ? 'message-chat-bubble mine' : 'message-chat-bubble'}>
                          <div className="message-bubble-header">
                            <strong>{isMine ? 'You' : item.sender_name}</strong>
                            <span>{new Date(item.created_at).toLocaleString()}</span>
                          </div>

                          {editingId === item.message_id ? (
                            <div className="form-stack">
                              <textarea
                                rows="4"
                                value={editingText}
                                onChange={(event) => setEditingText(event.target.value)}
                              />

                              <div className="button-group wrap-gap">
                                <button
                                  type="button"
                                  className="primary-btn"
                                  onClick={() => saveEdit(item.message_id)}
                                >
                                  Save
                                </button>

                                <button
                                  type="button"
                                  className="secondary-btn"
                                  onClick={cancelEdit}
                                >
                                  Cancel
                                </button>
                              </div>
                            </div>
                          ) : (
                            <p>{item.message}</p>
                          )}

                          {item.edited_at && (
                            <p className="muted small">Edited</p>
                          )}

                          <div className="message-action-row">
                            {isMine && editingId !== item.message_id && (
                              <button
                                type="button"
                                className="secondary-btn"
                                onClick={() => startEdit(item)}
                              >
                                Edit
                              </button>
                            )}

                            <button
                              type="button"
                              className="danger-btn"
                              onClick={() => deleteMessage(item.message_id)}
                            >
                              Delete
                            </button>
                          </div>
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}

              <form className="message-reply-box top-gap" onSubmit={sendReply}>
                <textarea
                  rows="4"
                  value={replyText}
                  onChange={(event) => setReplyText(event.target.value)}
                  placeholder="Write a reply..."
                />

                <button type="submit" className="primary-btn" disabled={sending}>
                  {sending ? 'Sending...' : 'Reply'}
                </button>
              </form>
            </>
          )}
        </section>
      </section>
    </div>
  );
}