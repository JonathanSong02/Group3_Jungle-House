import { useEffect, useState } from 'react';
import PageHeader from '../components/PageHeader';
import { useAuth } from '../context/AuthContext';

export default function Notifications() {
  const { user } = useAuth();
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    if (!user?.id) {
      setLoading(false);
      return;
    }

    const fetchNotifications = async () => {
      try {
        setLoading(true);
        setError('');

        const response = await fetch(`http://127.0.0.1:5000/api/notifications/${user.id}`);
        const data = await response.json();

        if (!response.ok) {
          throw new Error(data.message || 'Failed to load notifications.');
        }

        setItems(data);
      } catch (err) {
        setError(err.message || 'Unable to load notifications.');
      } finally {
        setLoading(false);
      }
    };

    fetchNotifications();
  }, [user]);

  const markAsRead = async (id) => {
    try {
      const response = await fetch(`http://127.0.0.1:5000/api/notifications/read/${id}`, {
        method: 'PUT',
      });

      const data = await response.json();

      if (!response.ok) {
        throw new Error(data.message || 'Failed to update notification.');
      }

      setItems((prev) =>
        prev.map((item) =>
          item.id === id ? { ...item, isRead: true } : item
        )
      );
    } catch (err) {
      setError(err.message || 'Unable to mark notification as read.');
    }
  };

  return (
    <div>
      <PageHeader
        title="Notifications"
        subtitle="System alerts for escalations, reviews, reminders, and announcements."
      />

      {loading ? <p className="muted">Loading notifications...</p> : null}
      {error ? <p className="error-text">{error}</p> : null}

      {!loading && !error && items.length === 0 ? (
        <div className="card-like">
          <p className="muted">No notifications yet.</p>
        </div>
      ) : null}

      <div className="stack-gap">
        {items.map((item) => (
          <article key={item.id} className="card-like row-between wrap-gap">
            <div>
              <p className="eyebrow">
                {item.isRead ? 'Read' : 'Unread'} · {item.type || 'system'}
              </p>
              <h3>{item.title}</h3>
              <p className="muted">{item.detail}</p>
              {item.created_at ? (
                <p className="muted small">
                  {new Date(item.created_at).toLocaleString()}
                </p>
              ) : null}
            </div>

            {!item.isRead ? (
              <button
                className="secondary-btn"
                onClick={() => markAsRead(item.id)}
              >
                Mark as read
              </button>
            ) : null}
          </article>
        ))}
      </div>
    </div>
  );
}