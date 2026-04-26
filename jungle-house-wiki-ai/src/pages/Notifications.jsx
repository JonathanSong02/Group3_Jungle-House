import { useEffect, useMemo, useState } from 'react';
import PageHeader from '../components/PageHeader';
import { useAuth } from '../context/AuthContext';
import api from '../services/api';

export default function Notifications() {
  const { user } = useAuth();

  const [items, setItems] = useState([]);
  const [filter, setFilter] = useState('all');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const fetchNotifications = async () => {
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
  };

  useEffect(() => {
    fetchNotifications();
  }, [user?.id]);

  const unreadCount = useMemo(() => {
    return items.filter((item) => !item.isRead).length;
  }, [items]);

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
    <div>
      <PageHeader
        title="Notifications"
        subtitle="System alerts for escalations, reviews, reminders, and announcements."
      />

      <section className="card-like notification-toolbar">
        <div>
          <h3>Notification Centre</h3>
          <p className="muted">
            You have <strong>{unreadCount}</strong> unread notification
            {unreadCount === 1 ? '' : 's'}.
          </p>
        </div>

        <div className="button-group notification-actions">
          <button
            className={filter === 'all' ? 'primary-btn' : 'secondary-btn'}
            onClick={() => setFilter('all')}
          >
            All
          </button>

          <button
            className={filter === 'unread' ? 'primary-btn' : 'secondary-btn'}
            onClick={() => setFilter('unread')}
          >
            Unread
          </button>

          <button
            className={filter === 'read' ? 'primary-btn' : 'secondary-btn'}
            onClick={() => setFilter('read')}
          >
            Read
          </button>

          <button className="secondary-btn" onClick={fetchNotifications}>
            Refresh
          </button>
        </div>
      </section>

      {loading && (
        <section className="card-like top-gap-sm">
          <p className="muted">Loading notifications...</p>
        </section>
      )}

      {error && (
        <section className="card-like danger-soft top-gap-sm">
          <p>{error}</p>
        </section>
      )}

      {!loading && !error && filteredItems.length === 0 && (
        <section className="card-like top-gap-sm empty-state-card">
          <h3>No notifications found</h3>
          <p className="muted">There are no notifications under this filter.</p>
        </section>
      )}

      <div className="stack-gap top-gap-sm">
        {filteredItems.map((item) => (
          <article
            key={item.id}
            className={
              item.isRead
                ? 'card-like notification-card'
                : 'card-like notification-card unread'
            }
          >
            <div className="notification-card-main">
              <div>
                <div className="notification-meta-row">
                  <span className={item.isRead ? 'status-badge resolved' : 'status-badge pending'}>
                    {item.isRead ? 'Read' : 'Unread'}
                  </span>

                  <span className="role-pill">
                    {item.type || 'system'}
                  </span>
                </div>

                <h3>{item.title}</h3>
                <p className="muted">{item.detail}</p>

                {item.created_at && (
                  <p className="muted small">
                    {new Date(item.created_at).toLocaleString()}
                  </p>
                )}
              </div>

              {!item.isRead && (
                <button
                  className="secondary-btn"
                  onClick={() => markAsRead(item.id)}
                >
                  Mark as read
                </button>
              )}
            </div>
          </article>
        ))}
      </div>
    </div>
  );
}