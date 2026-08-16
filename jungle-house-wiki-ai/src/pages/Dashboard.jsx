import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import PageHeader from '../components/PageHeader';
import api from '../services/api';

function DashboardIcon({ name }) {
  const props = {
    viewBox: '0 0 24 24',
    fill: 'none',
    stroke: 'currentColor',
    strokeWidth: '2',
    strokeLinecap: 'round',
    strokeLinejoin: 'round',
    'aria-hidden': 'true',
  };

  const icons = {
    chat: (
      <svg {...props}>
        <path d="M21 15a4 4 0 0 1-4 4H8l-5 3V7a4 4 0 0 1 4-4h10a4 4 0 0 1 4 4z" />
        <path d="M8 9h8" />
        <path d="M8 13h5" />
      </svg>
    ),
    knowledge: (
      <svg {...props}>
        <path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20" />
        <path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z" />
        <path d="M8 7h8" />
        <path d="M8 11h6" />
      </svg>
    ),
    notifications: (
      <svg {...props}>
        <path d="M18 8a6 6 0 1 0-12 0c0 7-3 7-3 7h18s-3 0-3-7" />
        <path d="M10 19a2 2 0 0 0 4 0" />
      </svg>
    ),
    alert: (
      <svg {...props}>
        <path d="M12 9v4" />
        <path d="M12 17h.01" />
        <path d="M10.3 3.9 2.5 17.3A2 2 0 0 0 4.2 20h15.6a2 2 0 0 0 1.7-2.7L13.7 3.9a2 2 0 0 0-3.4 0" />
      </svg>
    ),
    arrow: (
      <svg {...props}>
        <path d="M5 12h14" />
        <path d="m13 6 6 6-6 6" />
      </svg>
    ),
    sparkle: (
      <svg {...props}>
        <path d="m12 3-1.4 3.6L7 8l3.6 1.4L12 13l1.4-3.6L17 8l-3.6-1.4z" />
        <path d="m18 14-.8 2.2L15 17l2.2.8L18 20l.8-2.2L21 17l-2.2-.8z" />
      </svg>
    ),
  };

  return icons[name] || icons.sparkle;
}

const QUICK_ACTIONS = [
  {
    title: 'Ask AI',
    description: 'Get answers from verified Jungle House knowledge and SOPs.',
    route: '/chat',
    icon: 'chat',
    tone: 'primary',
  },
  {
    title: 'Knowledge Base',
    description: 'Browse SOPs, product information, and training resources.',
    route: '/knowledge',
    icon: 'knowledge',
    tone: 'secondary',
  },
  {
    title: 'Notifications',
    description: 'Review updates, approvals, escalations, and reminders.',
    route: '/notifications',
    icon: 'notifications',
    tone: 'neutral',
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
      <div className="dashboard-hero">
        <div className="dashboard-hero-copy">
          <span className="dashboard-hero-eyebrow">
            <DashboardIcon name="sparkle" />
            Jungle House Workspace
          </span>

          <PageHeader
            title="Dashboard"
            subtitle="Your central workspace for AI assistance, company knowledge, alerts, and training updates."
          />
        </div>

        <button
          type="button"
          className="dashboard-hero-action"
          onClick={() => navigate('/chat')}
        >
          <span className="dashboard-hero-action-icon">
            <DashboardIcon name="chat" />
          </span>
          <span>
            <small>Need help?</small>
            <strong>Ask Jungle House AI</strong>
          </span>
          <DashboardIcon name="arrow" />
        </button>
      </div>

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
                <span className="dashboard-skeleton-line" />
              </div>
            ))}
          </div>

          <div className="dashboard-skeleton-panel" aria-hidden="true">
            <span className="dashboard-skeleton-line short" />
            <span className="dashboard-skeleton-line" />
            <span className="dashboard-skeleton-line" />
          </div>

          <p className="dashboard-loading-text">Loading your workspace...</p>
        </div>
      ) : null}

      {!loading && error ? (
        <div className="dashboard-error-card" role="alert">
          <span className="dashboard-error-icon" aria-hidden="true">
            <DashboardIcon name="alert" />
          </span>

          <div>
            <strong>Unable to load dashboard</strong>
            <p>{error}</p>
          </div>
        </div>
      ) : null}

      {!loading && !error ? (
        <div className="dashboard-content">
          <section className="dashboard-overview" aria-label="Dashboard overview">
            <div className="dashboard-section-title-row">
              <div>
                <span className="dashboard-section-kicker">Overview</span>
                <h2>Workspace snapshot</h2>
              </div>
              <p>Live information from your Jungle House workspace.</p>
            </div>

            <div className="dashboard-stats-grid">
              {stats.map((item, index) => (
                <article
                  key={item.label}
                  className="dashboard-stat-card"
                >
                  <div className="dashboard-stat-top">
                    <span className="dashboard-stat-index">
                      {String(index + 1).padStart(2, '0')}
                    </span>
                    <span className="dashboard-stat-indicator" />
                  </div>

                  <span className="dashboard-stat-label">{item.label}</span>
                  <strong className="dashboard-stat-value">{item.value}</strong>
                  <span className="dashboard-stat-caption">Current overview</span>
                </article>
              ))}

              <article className="dashboard-stat-card dashboard-stat-card-ai">
                <div className="dashboard-stat-top">
                  <span className="dashboard-stat-ai-icon">
                    <DashboardIcon name="sparkle" />
                  </span>
                  <span className="dashboard-stat-indicator" />
                </div>

                <span className="dashboard-stat-label">AI Accuracy</span>
                <strong className="dashboard-stat-value">{ai.accuracy}</strong>
                <span className="dashboard-stat-caption">
                  Current AI performance
                </span>
              </article>
            </div>
          </section>

          {Number(pendingEscalations) > 0 ? (
            <div className="dashboard-alert" role="status">
              <span className="dashboard-alert-icon" aria-hidden="true">
                <DashboardIcon name="alert" />
              </span>

              <div className="dashboard-alert-copy">
                <strong>Escalations need attention</strong>
                <p>
                  You have {pendingEscalations} pending escalation
                  {Number(pendingEscalations) === 1 ? '' : 's'} requiring attention.
                </p>
              </div>

              <button
                type="button"
                className="dashboard-alert-action"
                onClick={() => navigate('/escalation')}
              >
                Review
                <DashboardIcon name="arrow" />
              </button>
            </div>
          ) : null}

          <section className="dashboard-section-card">
            <div className="dashboard-section-title-row">
              <div>
                <span className="dashboard-section-kicker">Shortcuts</span>
                <h2>Quick actions</h2>
              </div>
              <p>Jump directly to the tools you use most.</p>
            </div>

            <div className="dashboard-quick-actions">
              {QUICK_ACTIONS.map((action) => (
                <button
                  key={action.title}
                  type="button"
                  className={`dashboard-action-card dashboard-action-${action.tone}`}
                  onClick={() => navigate(action.route)}
                >
                  <span className="dashboard-action-icon">
                    <DashboardIcon name={action.icon} />
                  </span>

                  <span className="dashboard-action-copy">
                    <strong>{action.title}</strong>
                    <span>{action.description}</span>
                  </span>

                  <span className="dashboard-action-arrow">
                    <DashboardIcon name="arrow" />
                  </span>
                </button>
              ))}
            </div>
          </section>

          <div className="dashboard-feed-grid">
            <section className="dashboard-section-card dashboard-feed-card">
              <div className="dashboard-feed-header">
                <div>
                  <span className="dashboard-section-kicker">Updates</span>
                  <h2>Recent notifications</h2>
                </div>

                <button
                  type="button"
                  className="dashboard-text-action"
                  onClick={() => navigate('/notifications')}
                >
                  View all
                  <DashboardIcon name="arrow" />
                </button>
              </div>

              {notifications.length === 0 ? (
                <div className="dashboard-empty-state">
                  <span className="dashboard-empty-icon">
                    <DashboardIcon name="notifications" />
                  </span>
                  <strong>You&apos;re all caught up</strong>
                  <p>No recent notifications.</p>
                </div>
              ) : (
                <div className="dashboard-feed-list">
                  {notifications.map((item) => (
                    <article key={item.id} className="dashboard-feed-item">
                      <span className="dashboard-feed-marker">
                        <span />
                      </span>

                      <div className="dashboard-feed-content">
                        <strong>{item.title}</strong>
                        <p>{item.detail || item.message}</p>
                      </div>
                    </article>
                  ))}
                </div>
              )}
            </section>

            <section className="dashboard-section-card dashboard-feed-card">
              <div className="dashboard-feed-header">
                <div>
                  <span className="dashboard-section-kicker">Activity</span>
                  <h2>Recent activity</h2>
                </div>
              </div>

              {activities.length === 0 ? (
                <div className="dashboard-empty-state">
                  <span className="dashboard-empty-icon dashboard-empty-icon-secondary">
                    <DashboardIcon name="sparkle" />
                  </span>
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
                      <span className="dashboard-feed-marker dashboard-feed-marker-secondary">
                        <span />
                      </span>

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
