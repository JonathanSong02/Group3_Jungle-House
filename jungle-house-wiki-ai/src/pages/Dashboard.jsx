import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import PageHeader from '../components/PageHeader';
import api from '../services/api';

const QUICK_ACTIONS = [
  {
    title: 'Ask AI',
    description: 'Ask questions using verified Jungle House knowledge.',
    buttonLabel: 'Open AI Chat',
    route: '/chat',
    buttonClass: 'primary-btn',
  },
  {
    title: 'Browse Knowledge',
    description: 'Find SOPs, product information, and training content.',
    buttonLabel: 'Open Knowledge Base',
    route: '/knowledge',
    buttonClass: 'secondary-btn',
  },
  {
    title: 'Notifications',
    description: 'Check updates, approvals, escalations, and reminders.',
    buttonLabel: 'View Notifications',
    route: '/notifications',
    buttonClass: 'secondary-btn',
  },
];

function formatDateTime(value) {
  if (!value) return '';

  const date = new Date(value);

  if (Number.isNaN(date.getTime())) {
    return String(value);
  }

  return date.toLocaleString();
}

export default function Dashboard() {
  const navigate = useNavigate();

  const [stats, setStats] = useState([]);
  const [notifications, setNotifications] = useState([]);
  const [activities, setActivities] = useState([]);
  const [ai, setAi] = useState({ accuracy: '0%' });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    let cancelled = false;

    const fetchDashboard = async () => {
      try {
        setError('');

        const response = await api.get('/dashboard');
        const data = response.data;

        if (cancelled) return;

        setStats(Array.isArray(data.stats) ? data.stats : []);
        setNotifications(
          Array.isArray(data.notifications) ? data.notifications : []
        );
        setActivities(Array.isArray(data.activities) ? data.activities : []);
        setAi(data.ai || { accuracy: '0%' });
      } catch (err) {
        if (cancelled) return;

        console.error('Dashboard fetch error:', err);
        setError(
          err.response?.data?.error ||
            err.response?.data?.message ||
            err.message ||
            'Unable to load dashboard.'
        );
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    };

    fetchDashboard();

    return () => {
      cancelled = true;
    };
  }, []);

  const pendingEscalations =
    stats.find((item) => item.label === 'Pending Escalations')?.value || 0;

  return (
    <div className="dashboard-page">
      <PageHeader
        title="Dashboard"
        subtitle="Quick access to AI chat, knowledge, alerts, and training updates."
      />

      {loading ? (
        <div className="dashboard-loading" aria-live="polite">
          <div className="dashboard-skeleton-grid" aria-hidden="true">
            {Array.from({ length: 4 }).map((_, index) => (
              <div
                key={`dashboard-skeleton-${index}`}
                className="dashboard-skeleton-card"
              >
                <span className="dashboard-skeleton-line short" />
                <span className="dashboard-skeleton-line value" />
              </div>
            ))}
          </div>
          <p className="muted small">Loading dashboard...</p>
        </div>
      ) : null}

      {!loading && error ? (
        <div className="dashboard-error-card" role="alert">
          <div>
            <strong>Unable to load dashboard</strong>
            <p>{error}</p>
          </div>
        </div>
      ) : null}

      {!loading && !error ? (
        <div className="dashboard-content">
          <section aria-label="Dashboard overview">
            <div className="dashboard-stats-grid">
              {stats.map((item) => (
                <article
                  key={item.label}
                  className="card-like dashboard-stat-card"
                >
                  <span className="dashboard-stat-label">{item.label}</span>
                  <strong className="dashboard-stat-value">{item.value}</strong>
                  <span className="dashboard-stat-caption">Current overview</span>
                </article>
              ))}

              <article className="card-like dashboard-stat-card dashboard-stat-card-ai">
                <span className="dashboard-stat-label">AI Accuracy</span>
                <strong className="dashboard-stat-value">{ai.accuracy}</strong>
                <span className="dashboard-stat-caption">AI performance</span>
              </article>
            </div>
          </section>

          {Number(pendingEscalations) > 0 ? (
            <div className="dashboard-alert" role="status">
              <span className="dashboard-alert-icon" aria-hidden="true">
                !
              </span>
              <div>
                <strong>Escalations need attention</strong>
                <p>
                  You have {pendingEscalations} pending escalation
                  {Number(pendingEscalations) === 1 ? '' : 's'} requiring attention.
                </p>
              </div>
            </div>
          ) : null}

          <section className="card-like dashboard-section-card">
            <div className="dashboard-section-heading">
              <div>
                <span className="eyebrow">Shortcuts</span>
                <h3>Quick Actions</h3>
                <p>Go directly to the tools you use most often.</p>
              </div>
            </div>

            <div className="dashboard-quick-actions">
              {QUICK_ACTIONS.map((action) => (
                <article key={action.title} className="dashboard-action-card">
                  <div>
                    <h4>{action.title}</h4>
                    <p>{action.description}</p>
                  </div>

                  <button
                    type="button"
                    className={action.buttonClass}
                    onClick={() => navigate(action.route)}
                  >
                    {action.buttonLabel}
                  </button>
                </article>
              ))}
            </div>
          </section>

          <div className="dashboard-feed-grid">
            <section className="card-like dashboard-section-card dashboard-feed-card">
              <div className="dashboard-section-heading dashboard-section-heading-row">
                <div>
                  <span className="eyebrow">Updates</span>
                  <h3>Recent Notifications</h3>
                </div>

                <button
                  type="button"
                  className="text-link dashboard-heading-link"
                  onClick={() => navigate('/notifications')}
                >
                  View all
                </button>
              </div>

              {notifications.length === 0 ? (
                <div className="dashboard-empty-state">
                  <strong>You&apos;re all caught up</strong>
                  <p>No recent notifications.</p>
                </div>
              ) : (
                <div className="dashboard-feed-list">
                  {notifications.map((item) => (
                    <article key={item.id} className="dashboard-feed-item">
                      <span className="dashboard-feed-dot" aria-hidden="true" />
                      <div className="dashboard-feed-content">
                        <strong>{item.title}</strong>
                        <p>{item.detail || item.message}</p>
                      </div>
                    </article>
                  ))}
                </div>
              )}
            </section>

            <section className="card-like dashboard-section-card dashboard-feed-card">
              <div className="dashboard-section-heading">
                <div>
                  <span className="eyebrow">Activity</span>
                  <h3>Recent Activity</h3>
                </div>
              </div>

              {activities.length === 0 ? (
                <div className="dashboard-empty-state">
                  <strong>No activity yet</strong>
                  <p>Recent account and system activity will appear here.</p>
                </div>
              ) : (
                <div className="dashboard-feed-list">
                  {activities.map((item, index) => (
                    <article
                      key={`${item.action}-${index}`}
                      className="dashboard-feed-item"
                    >
                      <span
                        className="dashboard-feed-dot dashboard-feed-dot-secondary"
                        aria-hidden="true"
                      />
                      <div className="dashboard-feed-content">
                        <strong>{item.action}</strong>
                        {item.created_at ? (
                          <time dateTime={item.created_at}>
                            {formatDateTime(item.created_at)}
                          </time>
                        ) : null}
                      </div>
                    </article>
                  ))}
                </div>
              )}
            </section>
          </div>
        </div>
      ) : null}
    </div>
  );
}
