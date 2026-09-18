import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import PageHeader from '../components/PageHeader';
import { useAuth } from '../context/AuthContext';
import api from '../services/api';
import '../styles/Notifications.css';

function formatNotificationDate(value) {
  if (!value) return null;
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return null;
  return { label: date.toLocaleString(), iso: date.toISOString() };
}

function getNotificationIcon(type, title = '') {
  const value = String(type || 'system').toLowerCase();
  const heading = String(title || '').toLowerCase();

  // The backend stores registration alerts as type=system.
  if (heading.includes('account approval') || heading.includes('registration')) return 'U';
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
  const userId = user?.id ?? user?.user_id ?? null;
  const role = String(user?.role || user?.role_name || '').toLowerCase().replace(/[\s_-]/g, '');
  const canReviewRegistrations = ['manager', 'admin', 'teamlead'].includes(role);

  // Keep notifications tied to the session account, not a previous login.
  const [notificationData, setNotificationData] = useState({ userId: null, items: [] });
  const items = notificationData.userId === userId ? notificationData.items : [];
  const [filter, setFilter] = useState('all');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [actionError, setActionError] = useState('');
  const [markingId, setMarkingId] = useState(null);
  const requestVersionRef = useRef(0);
  const currentUserIdRef = useRef(userId);
  const markInFlightRef = useRef(null);
  currentUserIdRef.current = userId;

  const fetchNotifications = useCallback(async () => {
    const requestVersion = ++requestVersionRef.current;
    if (userId == null) {
      setNotificationData({ userId: null, items: [] });
      setError('');
      setLoading(false);
      return;
    }

    setLoading(true);
    setError('');

    try {
      // Flask enforces that this URL's user ID matches the verified session.
      const response = await api.get(`/notifications/${userId}`);
      if (requestVersion !== requestVersionRef.current || currentUserIdRef.current !== userId) return;
      const receivedItems = Array.isArray(response.data) ? response.data : [];
      setNotificationData({
        userId,
        items: receivedItems.map((item) => ({
          ...item,
          isRead: item.isRead === true || item.isRead === 1 || item.isRead === '1',
        })),
      });
    } catch (err) {
      if (requestVersion !== requestVersionRef.current || currentUserIdRef.current !== userId) return;
      console.error('Fetch notifications error:', err);
      const code = err.response?.data?.code;
      setError(
        code === 'SESSION_EXPIRED' || err.response?.status === 401
          ? 'Your session has expired. Please sign in again.'
          : err.response?.data?.message || 'Unable to load notifications.'
      );
      // Do not display outdated summary counts after a failed reload.
      setNotificationData((prev) => prev.userId === userId ? { userId, items: [] } : prev);
    } finally {
      if (requestVersion === requestVersionRef.current && currentUserIdRef.current === userId) {
        setLoading(false);
      }
    }
  }, [userId]);

  useEffect(() => {
    setActionError('');
    setMarkingId(null);
    markInFlightRef.current = null;
    fetchNotifications();
    return () => { requestVersionRef.current += 1; };
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
    if (userId == null || markInFlightRef.current?.userId === userId) return;
    const requestUserId = userId;
    const operation = { userId, id };
    markInFlightRef.current = operation;
    setMarkingId(id);
    setActionError('');

    try {
      await api.put(`/notifications/read/${id}`);
      if (currentUserIdRef.current !== requestUserId || markInFlightRef.current !== operation) return;
      // A GET started before this PUT must never overwrite the confirmed read state.
      requestVersionRef.current += 1;
      setLoading(false);
      setNotificationData((prev) => prev.userId === requestUserId
        ? {
            ...prev,
            items: prev.items.map((item) => String(item.id) === String(id) ? { ...item, isRead: true } : item),
          }
        : prev
      );
    } catch (err) {
      if (currentUserIdRef.current !== requestUserId || markInFlightRef.current !== operation) return;
      console.error('Mark notification error:', err);
      setActionError(err.response?.data?.message || 'Unable to mark notification as read.');
    } finally {
      if (markInFlightRef.current === operation) {
        markInFlightRef.current = null;
        if (currentUserIdRef.current === requestUserId) setMarkingId(null);
      }
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
                aria-pressed={filter === 'all'}
              >
                All
                <span>{items.length}</span>
              </button>

              <button
                type="button"
                className={filter === 'unread' ? 'active' : ''}
                onClick={() => setFilter('unread')}
                aria-pressed={filter === 'unread'}
              >
                Unread
                <span>{unreadCount}</span>
              </button>

              <button
                type="button"
                className={filter === 'read' ? 'active' : ''}
                onClick={() => setFilter('read')}
                aria-pressed={filter === 'read'}
              >
                Read
                <span>{readCount}</span>
              </button>
            </div>

            <button
              type="button"
              className="notification-refresh-btn"
              onClick={fetchNotifications}
              disabled={loading || markingId !== null || userId == null}
              aria-label="Refresh notifications"
            >
              Refresh
            </button>
          </div>
        </div>

        {loading && (
          <div className="notifications-state-card" role="status">
            <div className="notifications-state-icon">•••</div>
            <strong>Loading notifications</strong>
          </div>
        )}

        {!loading && error && (
          <div className="notifications-state-card error" role="alert">
            <div className="notifications-state-icon">!</div>
            <strong>Unable to load notifications</strong>
            <p>{error}</p>
          </div>
        )}

        {actionError && (
          <div className="notifications-state-card error" role="alert">
            <p>{actionError}</p>
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
                  {getNotificationIcon(item.type, item.title)}
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

                    {formatNotificationDate(item.created_at) && (
                      <time
                        className="notification-time"
                        dateTime={formatNotificationDate(item.created_at).iso}
                      >
                        {formatNotificationDate(item.created_at).label}
                      </time>
                    )}
                  </div>

                  <h3>{item.title || 'Notification'}</h3>
                  <p>{item.detail || ''}</p>
                </div>

                {canReviewRegistrations && item.title === 'New account approval needed' ? (
                  <Link to="/admin/users" className="notification-mark-btn">
                    Review account
                  </Link>
                ) : null}

                {!item.isRead && (
                  <button
                    type="button"
                    className="notification-mark-btn"
                    onClick={() => markAsRead(item.id)}
                    disabled={markingId !== null}
                  >
                    {markingId === item.id ? 'Saving...' : 'Mark read'}
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
