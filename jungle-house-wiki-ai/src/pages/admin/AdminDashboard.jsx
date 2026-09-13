import { useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { useAuth } from '../../context/AuthContext';
import api from '../../services/api';
import './styles/AdminDashboard.css';

const QUICK_ACTIONS = [
  { title: 'Users', route: '/admin/users', icon: 'users' },
  { title: 'Content', route: '/admin/content', icon: 'knowledge' },
  { title: 'Reviews', route: '/admin/review', icon: 'review' },
  { title: 'Quiz', route: '/admin/quiz-management', icon: 'quiz' },
  { title: 'AI Settings', route: '/admin/ai-settings', icon: 'settings' },
  { title: 'Notion', route: '/admin/notion-sync', icon: 'sync' },
];

function DashboardIcon({ name }) {
  const commonProps = {
    width: 22,
    height: 22,
    viewBox: '0 0 24 24',
    fill: 'none',
    stroke: 'currentColor',
    strokeWidth: 1.9,
    strokeLinecap: 'round',
    strokeLinejoin: 'round',
    'aria-hidden': true,
  };

  switch (name) {
    case 'knowledge':
      return (
        <svg {...commonProps}>
          <path d="M4 5.5A2.5 2.5 0 0 1 6.5 3H20v15H6.5A2.5 2.5 0 0 0 4 20.5z" />
          <path d="M4 5.5v15A2.5 2.5 0 0 0 6.5 23H20" />
          <path d="M8 7h7M8 11h8" />
        </svg>
      );

    case 'review':
      return (
        <svg {...commonProps}>
          <path d="M9 11l2 2 4-5" />
          <path d="M6 3h12a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2z" />
          <path d="M8 17h8" />
        </svg>
      );

    case 'users':
      return (
        <svg {...commonProps}>
          <path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2" />
          <circle cx="9" cy="7" r="4" />
          <path d="M22 21v-2a4 4 0 0 0-3-3.87M16 3.13a4 4 0 0 1 0 7.75" />
        </svg>
      );

    case 'quiz':
      return (
        <svg {...commonProps}>
          <path d="M9 11a3 3 0 1 1 5.83 1c-.83 1.5-2.83 1.5-2.83 3" />
          <path d="M12 19h.01" />
          <rect x="3" y="2" width="18" height="20" rx="3" />
        </svg>
      );

    case 'sync':
      return (
        <svg {...commonProps}>
          <path d="M20 7h-5V2" />
          <path d="M4 17h5v5" />
          <path d="M5.8 8A7 7 0 0 1 18.5 5L20 7M4 17l1.5 2A7 7 0 0 0 18.2 16" />
        </svg>
      );

    case 'settings':
      return (
        <svg {...commonProps}>
          <circle cx="12" cy="12" r="3" />
          <path d="M19.4 15a1.7 1.7 0 0 0 .34 1.88l.06.06-2.83 2.83-.06-.06A1.7 1.7 0 0 0 15 19.4a1.7 1.7 0 0 0-1 .6 1.7 1.7 0 0 0-.4 1.1V21h-4v-.1a1.7 1.7 0 0 0-1.1-1.5 1.7 1.7 0 0 0-1.88.34l-.06.06-2.83-2.83.06-.06A1.7 1.7 0 0 0 4.6 15a1.7 1.7 0 0 0-.6-1 1.7 1.7 0 0 0-1.1-.4H3v-4h.1A1.7 1.7 0 0 0 4.6 8.5a1.7 1.7 0 0 0-.34-1.88l-.06-.06 2.83-2.83.06.06A1.7 1.7 0 0 0 9 4.6a1.7 1.7 0 0 0 1-.6 1.7 1.7 0 0 0 .4-1.1V3h4v.1A1.7 1.7 0 0 0 15.5 4.6a1.7 1.7 0 0 0 1.88-.34l.06-.06 2.83 2.83-.06.06A1.7 1.7 0 0 0 19.4 9c.4.3.6.65.6 1.1v.1h1v4h-.1A1.7 1.7 0 0 0 19.4 15z" />
        </svg>
      );

    case 'question':
      return (
        <svg {...commonProps}>
          <circle cx="12" cy="12" r="9" />
          <path d="M9.8 9a2.5 2.5 0 1 1 3.9 2.1c-1.2.8-1.7 1.2-1.7 2.4" />
          <path d="M12 17h.01" />
        </svg>
      );

    case 'bell':
      return (
        <svg {...commonProps}>
          <path d="M18 8a6 6 0 0 0-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9" />
          <path d="M10 21h4" />
        </svg>
      );

    case 'shield':
      return (
        <svg {...commonProps}>
          <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
          <path d="m9 12 2 2 4-4" />
        </svg>
      );

    default:
      return (
        <svg {...commonProps}>
          <circle cx="12" cy="12" r="9" />
          <path d="M8 12h8M12 8v8" />
        </svg>
      );
  }
}

function formatDateTime(value) {
  if (!value) return '';
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? String(value) : date.toLocaleString();
}

function parsePercent(value) {
  const parsed = Number.parseFloat(String(value || '').replace('%', ''));
  if (!Number.isFinite(parsed)) return 0;
  return Math.min(100, Math.max(0, parsed));
}

export default function AdminDashboard() {
  const { user } = useAuth();

  const [stats, setStats] = useState([]);
  const [users, setUsers] = useState([]);
  const [notifications, setNotifications] = useState([]);
  const [activities, setActivities] = useState([]);
  const [ai, setAi] = useState({ accuracy: '0%' });

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    let cancelled = false;

    const loadDashboard = async () => {
      try {
        const [dashboardResponse, usersResponse] = await Promise.all([
          api.get('/dashboard'),
          api.get('/admin/users'),
        ]);

        if (cancelled) return;

        const dashboardData = dashboardResponse.data || {};
        setStats(Array.isArray(dashboardData.stats) ? dashboardData.stats : []);
        setNotifications(
          Array.isArray(dashboardData.notifications)
            ? dashboardData.notifications
            : []
        );
        setActivities(
          Array.isArray(dashboardData.activities)
            ? dashboardData.activities
            : []
        );
        setAi(dashboardData.ai || { accuracy: '0%' });

        setUsers(
          Array.isArray(usersResponse.data)
            ? usersResponse.data
            : []
        );
      } catch (requestError) {
        if (cancelled) return;

        console.error('Admin dashboard fetch error:', requestError);

        setError(
          requestError.response?.data?.message ||
            requestError.response?.data?.error ||
            'Some dashboard data is unavailable.'
        );
      } finally {
        if (!cancelled) setLoading(false);
      }
    };

    loadDashboard();

    return () => {
      cancelled = true;
    };
  }, []);

  const statMap = useMemo(
    () => Object.fromEntries(stats.map((item) => [item.label, item.value])),
    [stats]
  );

  const articles = Number(statMap['Knowledge Articles'] || 0);
  const weeklyQuestions = Number(statMap['Questions This Week'] || 0);
  const pendingEscalations = Number(statMap['Pending Escalations'] || 0);
  const unreadNotifications = Number(statMap['Unread Notifications'] || 0);

  const totalUsers = users.length;
  const pendingUsers = users.filter(
    (item) => item.status === 'pending' && !item.awaiting_activation
  ).length;

  const confidence = parsePercent(ai.accuracy);
  const managerName = user?.name || user?.full_name || 'Manager';

  const overviewCards = [
    {
      label: 'Users',
      value: totalUsers,
      route: '/admin/users',
      icon: 'users',
      tone: 'blue',
    },
    {
      label: 'Pending',
      value: pendingUsers,
      route: '/admin/users',
      icon: 'review',
      tone: pendingUsers > 0 ? 'amber' : 'green',
    },
    {
      label: 'Articles',
      value: articles,
      route: '/admin/content',
      icon: 'knowledge',
      tone: 'green',
    },
    {
      label: 'Escalations',
      value: pendingEscalations,
      route: '/escalation',
      icon: 'question',
      tone: pendingEscalations > 0 ? 'amber' : 'slate',
    },
  ];

  return (
    <div className="hd-admin-page hd-admin-page-compact">
      <header className="hd-admin-page-header compact">
        <div>
          <span className="hd-admin-overline">Admin Dashboard</span>
          <h1>Welcome back, {managerName}</h1>
          <p>System overview and quick actions.</p>
        </div>

        <div className="hd-admin-header-actions">
          <Link to="/chat" className="hd-admin-btn hd-admin-btn-ghost">
            <DashboardIcon name="question" />
            Ask AI
          </Link>

          <Link
            to="/admin/content/add"
            className="hd-admin-btn hd-admin-btn-primary"
          >
            <span className="hd-admin-btn-plus">+</span>
            Add Article
          </Link>
        </div>
      </header>

      {error ? (
        <div className="hd-admin-data-notice" role="status">
          <DashboardIcon name="bell" />
          <span>{error}</span>
        </div>
      ) : null}

      <section
        className="hd-admin-overview-grid compact"
        aria-label="System overview"
      >
        {overviewCards.map((item) => (
          <Link
            key={item.label}
            to={item.route}
            className={`hd-admin-metric compact hd-tone-${item.tone}`}
          >
            <div className="hd-admin-metric-top">
              <span className="hd-admin-metric-icon">
                <DashboardIcon name={item.icon} />
              </span>

              <span className="hd-admin-metric-label">{item.label}</span>
            </div>

            <strong className="hd-admin-metric-value">
              {loading ? '—' : item.value}
            </strong>

            <span className="hd-admin-metric-link">Open →</span>
          </Link>
        ))}
      </section>

      <section className="hd-admin-pulse-row">
        <div className="hd-admin-pulse-item">
          <span>AI Confidence</span>
          <strong>{loading ? '—' : ai.accuracy || '0%'}</strong>
          <div className="hd-admin-pulse-track" aria-hidden="true">
            <span style={{ width: `${confidence}%` }} />
          </div>
        </div>

        <div className="hd-admin-pulse-item">
          <span>Questions This Week</span>
          <strong>{loading ? '—' : weeklyQuestions}</strong>
        </div>

        <div className="hd-admin-pulse-item">
          <span>Notifications</span>
          <strong>{loading ? '—' : unreadNotifications}</strong>
        </div>
      </section>

      <section className="hd-admin-section-block">
        <div className="hd-admin-section-title">
          <div>
            <h2>Quick Actions</h2>
            <p>Go directly to a management area.</p>
          </div>
        </div>

        <div className="hd-admin-quick-grid">
          {QUICK_ACTIONS.map((item) => (
            <Link
              key={item.title}
              to={item.route}
              className="hd-admin-quick-card"
            >
              <span className="hd-admin-quick-icon">
                <DashboardIcon name={item.icon} />
              </span>

              <strong>{item.title}</strong>
              <span className="hd-admin-quick-arrow">→</span>
            </Link>
          ))}
        </div>
      </section>

      <section className="hd-admin-info-grid">
        <article className="hd-admin-panel compact">
          <div className="hd-admin-panel-heading compact">
            <div>
              <h3>Recent Activity</h3>
            </div>

            <Link
              to="/admin/security"
              className="hd-admin-inline-link"
            >
              View all
            </Link>
          </div>

          {loading ? (
            <div className="hd-admin-skeleton-list">
              <span />
              <span />
              <span />
            </div>
          ) : activities.length === 0 ? (
            <div className="hd-admin-empty-state compact">
              <strong>No recent activity</strong>
            </div>
          ) : (
            <div className="hd-admin-activity-list compact">
              {activities.slice(0, 4).map((item, index) => (
                <div
                  key={`${item.action}-${index}`}
                  className="hd-admin-activity-item compact"
                >
                  <span
                    className="hd-admin-activity-marker"
                    aria-hidden="true"
                  />

                  <div>
                    <strong>{item.action}</strong>

                    {item.created_at ? (
                      <time dateTime={item.created_at}>
                        {formatDateTime(item.created_at)}
                      </time>
                    ) : null}
                  </div>
                </div>
              ))}
            </div>
          )}
        </article>

        <article className="hd-admin-panel compact">
          <div className="hd-admin-panel-heading compact">
            <div>
              <h3>Notifications</h3>
            </div>

            <span className="hd-admin-panel-count hd-admin-panel-count-soft">
              {unreadNotifications}
            </span>
          </div>

          {loading ? (
            <div className="hd-admin-skeleton-list">
              <span />
              <span />
              <span />
            </div>
          ) : notifications.length === 0 ? (
            <div className="hd-admin-empty-state compact">
              <strong>No new notifications</strong>
            </div>
          ) : (
            <div className="hd-admin-notification-list compact">
              {notifications.slice(0, 4).map((item) => (
                <div
                  key={item.id}
                  className="hd-admin-notification-item compact"
                >
                  <span
                    className="hd-admin-notification-dot"
                    aria-hidden="true"
                  />

                  <div>
                    <strong>{item.title}</strong>
                    <p>{item.detail || item.message || 'System update'}</p>
                  </div>
                </div>
              ))}
            </div>
          )}
        </article>
      </section>
    </div>
  );
}
