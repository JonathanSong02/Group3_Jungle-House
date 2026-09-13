import { useCallback, useEffect, useMemo, useState } from 'react';
import PageHeader from '../components/PageHeader';
import { useAuth } from '../context/AuthContext';
import api from '../services/api';
import '../styles/Notifications.css';

function getNotificationIcon(type) {
  const value = String(type || 'system').toLowerCase();

  if (value.includes('review')) return '✓';
  if (value.includes('message')) return '✉';
  if (value.includes('quiz')) return 'Q';
  if (value.includes('registration')) return 'U';
  if (value.includes('escalation')) return '!';
  if (value.includes('announcement')) return 'A';

  return '•';
}

export default function Notifications() {
  const { user } = useAuth();

  const [items, setItems] = useState([]);
  const [filter, setFilter] = useState('all');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const fetchNotifications = useCallback(async () => {
    if (!user?.id) {
      setLoading(false);
      return;
    }

    try {
      setLoading(true);
      setError('');

      const response = await api.get(`/notifications/${user.id}`);
      setItems(Array.isArray(response.data) ? response.data : []);
    } catch (err) {
      console.error('Fetch notifications error:', err);
      setError(err.response?.data?.message || 'Unable to load notifications.');
    } finally {
      setLoading(false);
    }
  }, [user?.id]);

  useEffect(() => {
    fetchNotifications();
  }, [fetchNotifications]);

  const unreadCount = useMemo(() => {
    return items.filter((item) => !item.isRead).length;
  }, [items]);

  const readCount = items.length - unreadCount;

  const filteredItems = useMemo(() => {
    if (filter === 'unread') {
      return items.filter((item) => !item.isRead);
    }

    if (filter === 'read') {
      return items.filter((item) => item.isRead);
    }

    return items;
  }, [items, filter]);

  const markAsRead = async (id) => {
    try {
      setError('');

      await api.put(`/notifications/read/${id}`);

      setItems((prev) =>
        prev.map((item) =>
          item.id === id ? { ...item, isRead: true } : item
        )
      );
    } catch (err) {
      console.error('Mark notification error:', err);
      setError(err.response?.data?.message || 'Unable to mark notification as read.');
    }
  };

  return (
    <div className="notifications-page">
      <PageHeader
        title="Notifications"
        subtitle="Your latest system updates and alerts."
      />

      <section className="notifications-summary-grid">
        <div className="notifications-summary-card total">
          <span>Total</span>
          <strong>{items.length}</strong>
        </div>

        <div className="notifications-summary-card unread">
          <span>Unread</span>
          <strong>{unreadCount}</strong>
        </div>

        <div className="notifications-summary-card read">
          <span>Read</span>
          <strong>{readCount}</strong>
        </div>
      </section>

      <section className="notifications-workspace">
        <div className="notifications-toolbar">
          <div className="notifications-toolbar-title">
            <span className="notifications-kicker">Activity Centre</span>
            <h2>Recent Updates</h2>
          </div>

          <div className="notification-actions">
            <div className="notification-filter-tabs">
              <button
                type="button"
                className={filter === 'all' ? 'active' : ''}
                onClick={() => setFilter('all')}
              >
                All
                <span>{items.length}</span>
              </button>

              <button
                type="button"
                className={filter === 'unread' ? 'active' : ''}
                onClick={() => setFilter('unread')}
              >
                Unread
                <span>{unreadCount}</span>
              </button>

              <button
                type="button"
                className={filter === 'read' ? 'active' : ''}
                onClick={() => setFilter('read')}
              >
                Read
                <span>{readCount}</span>
              </button>
            </div>

            <button
              type="button"
              className="notification-refresh-btn"
              onClick={fetchNotifications}
            >
              Refresh
            </button>
          </div>
        </div>

        {loading && (
          <div className="notifications-state-card">
            <div className="notifications-state-icon">•••</div>
            <strong>Loading notifications</strong>
          </div>
        )}

        {error && (
          <div className="notifications-state-card error" role="alert">
            <div className="notifications-state-icon">!</div>
            <strong>Unable to load notifications</strong>
            <p>{error}</p>
          </div>
        )}

        {!loading && !error && filteredItems.length === 0 && (
          <div className="notifications-state-card">
            <div className="notifications-state-icon">✓</div>
            <strong>No notifications found</strong>
            <p>Nothing to show under this filter.</p>
          </div>
        )}

        {!loading && !error && filteredItems.length > 0 && (
          <div className="notifications-list">
            {filteredItems.map((item) => (
              <article
                key={item.id}
                className={`notification-card ${item.isRead ? 'read' : 'unread'}`}
              >
                <div className={`notification-icon ${item.isRead ? 'read' : 'unread'}`}>
                  {getNotificationIcon(item.type)}
                </div>

                <div className="notification-content">
                  <div className="notification-top-row">
                    <div className="notification-meta-row">
                      <span className={`notification-status ${item.isRead ? 'read' : 'unread'}`}>
                        {item.isRead ? 'Read' : 'New'}
                      </span>

                      <span className="notification-type">
                        {item.type || 'system'}
                      </span>
                    </div>

                    {item.created_at && (
                      <time className="notification-time">
                        {new Date(item.created_at).toLocaleString()}
                      </time>
                    )}
                  </div>

                  <h3>{item.title}</h3>
                  <p>{item.detail}</p>
                </div>

                {!item.isRead && (
                  <button
                    type="button"
                    className="notification-mark-btn"
                    onClick={() => markAsRead(item.id)}
                  >
                    Mark read
                  </button>
                )}
              </article>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}
