import { useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { useAuth } from '../../context/AuthContext';
import api from '../../services/api';
import './styles/AdminDashboard.css';

const MANAGEMENT_MODULES = [
  {
    title: 'Content Management',
    description: 'Create, organise, verify, and maintain Jungle House knowledge.',
    route: '/admin/content',
    label: 'Knowledge',
    icon: 'knowledge',
    tone: 'green',
  },
  {
    title: 'Review Management',
    description: 'Review human answers before they become trusted knowledge.',
    route: '/admin/review',
    label: 'Governance',
    icon: 'review',
    tone: 'amber',
  },
  {
    title: 'User Management',
    description: 'Manage account access, approval status, and staff roles.',
    route: '/admin/users',
    label: 'People',
    icon: 'users',
    tone: 'blue',
  },
  {
    title: 'Security Monitoring',
    description: 'Inspect login activity, audit events, and system access.',
    route: '/admin/security',
    label: 'Security',
    icon: 'shield',
    tone: 'red',
  },
  {
    title: 'Quiz Management',
    description: 'Manage training quizzes and knowledge-check content.',
    route: '/admin/quiz-management',
    label: 'Training',
    icon: 'quiz',
    tone: 'purple',
  },
  {
    title: 'Notion Sync',
    description: 'Control imported knowledge and synchronisation with Notion.',
    route: '/admin/notion-sync',
    label: 'Integration',
    icon: 'sync',
    tone: 'slate',
  },
  {
    title: 'Analytics',
    description: 'Review system usage, knowledge trends, and AI activity.',
    route: '/admin/analytics',
    label: 'Insights',
    icon: 'analytics',
    tone: 'teal',
  },
  {
    title: 'AI Model Settings',
    description: 'Manage AI provider behaviour and workspace configuration.',
    route: '/admin/ai-settings',
    label: 'AI Control',
    icon: 'settings',
    tone: 'gold',
  },
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
    case 'shield':
      return (
        <svg {...commonProps}>
          <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
          <path d="m9 12 2 2 4-4" />
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
    case 'analytics':
      return (
        <svg {...commonProps}>
          <path d="M4 20V10M10 20V4M16 20v-7M22 20H2" />
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
  const [notifications, setNotifications] = useState([]);
  const [activities, setActivities] = useState([]);
  const [ai, setAi] = useState({ accuracy: '0%' });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    let cancelled = false;

    const loadDashboard = async () => {
      try {
        const response = await api.get('/dashboard');
        if (cancelled) return;

        const data = response.data || {};
        setStats(Array.isArray(data.stats) ? data.stats : []);
        setNotifications(Array.isArray(data.notifications) ? data.notifications : []);
        setActivities(Array.isArray(data.activities) ? data.activities : []);
        setAi(data.ai || { accuracy: '0%' });
      } catch (requestError) {
        if (cancelled) return;
        console.error('Admin dashboard fetch error:', requestError);
        setError(
          requestError.response?.data?.message ||
            requestError.response?.data?.error ||
            'Live dashboard data is temporarily unavailable.'
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
  const confidence = parsePercent(ai.accuracy);
  const managerName = user?.name || user?.full_name || 'Manager';

  const overviewCards = [
    {
      label: 'Knowledge Articles',
      value: articles,
      caption: 'Available knowledge records',
      icon: 'knowledge',
      tone: 'green',
    },
    {
      label: 'Questions This Week',
      value: weeklyQuestions,
      caption: 'Recent knowledge demand',
      icon: 'question',
      tone: 'blue',
    },
    {
      label: 'Pending Escalations',
      value: pendingEscalations,
      caption: pendingEscalations > 0 ? 'Require human attention' : 'No pending review',
      icon: 'review',
      tone: pendingEscalations > 0 ? 'amber' : 'green',
    },
    {
      label: 'Unread Notifications',
      value: unreadNotifications,
      caption: 'System and workflow updates',
      icon: 'bell',
      tone: unreadNotifications > 0 ? 'purple' : 'slate',
    },
  ];

  return (
    <div className="hd-admin-page">
      <header className="hd-admin-page-header">
        <div>
          <span className="hd-admin-overline">Manager workspace</span>
          <h1>Welcome back, {managerName}</h1>
          <p>
            Monitor knowledge quality, AI activity, team workflows, and system governance
            from one operational view.
          </p>
        </div>

        <div className="hd-admin-header-actions">
          <Link to="/chat" className="hd-admin-btn hd-admin-btn-ghost">
            <DashboardIcon name="question" />
            Ask AI
          </Link>
          <Link to="/admin/content/add" className="hd-admin-btn hd-admin-btn-primary">
            <span className="hd-admin-btn-plus">+</span>
            Add article
          </Link>
        </div>
      </header>

      {error ? (
        <div className="hd-admin-data-notice" role="status">
          <strong>Dashboard is showing limited live data.</strong>
          <span>{error}</span>
        </div>
      ) : null}

      <section className="hd-admin-hero" aria-label="Admin control centre overview">
        <div className="hd-admin-hero-copy">
          <span className="hd-admin-live-pill">
            <span className="hd-admin-live-dot" aria-hidden="true" />
            Knowledge operations
          </span>
          <h2>Jungle House AI Wiki Control Centre</h2>
          <p>
            Keep trusted knowledge current, resolve unanswered questions, and maintain the
            quality of the AI experience used by Jungle House staff.
          </p>

          <div className="hd-admin-hero-links">
            <Link to="/escalation">Review escalations <span>→</span></Link>
            <Link to="/admin/review">Open review queue <span>→</span></Link>
          </div>
        </div>

        <div className="hd-admin-confidence-card">
          <div
            className="hd-admin-confidence-ring"
            style={{ '--hd-confidence': `${confidence * 3.6}deg` }}
            aria-label={`AI confidence ${ai.accuracy || '0%'}`}
          >
            <div className="hd-admin-confidence-ring-inner">
              <strong>{loading ? '—' : ai.accuracy || '0%'}</strong>
              <span>AI confidence</span>
            </div>
          </div>

          <div className="hd-admin-confidence-copy">
            <span>Knowledge pulse</span>
            <strong>{weeklyQuestions} questions this week</strong>
            <p>Confidence is calculated from recorded AI responses.</p>
          </div>
        </div>
      </section>

      <section className="hd-admin-overview-grid" aria-label="System overview">
        {overviewCards.map((item) => (
          <article key={item.label} className={`hd-admin-metric hd-tone-${item.tone}`}>
            <div className="hd-admin-metric-top">
              <span className="hd-admin-metric-icon">
                <DashboardIcon name={item.icon} />
              </span>
              <span className="hd-admin-metric-label">{item.label}</span>
            </div>
            <strong className="hd-admin-metric-value">{loading ? '—' : item.value}</strong>
            <span className="hd-admin-metric-caption">{item.caption}</span>
          </article>
        ))}
      </section>

      <section className="hd-admin-main-grid">
        <article className="hd-admin-panel hd-admin-attention-panel">
          <div className="hd-admin-panel-heading">
            <div>
              <span className="hd-admin-panel-overline">Priority queue</span>
              <h3>Needs your attention</h3>
            </div>
            <span className="hd-admin-panel-count">
              {loading ? '—' : pendingEscalations + unreadNotifications}
            </span>
          </div>

          <div className="hd-admin-attention-list">
            <Link to="/escalation" className="hd-admin-attention-item">
              <span className="hd-admin-attention-icon hd-tone-amber">
                <DashboardIcon name="review" />
              </span>
              <div>
                <strong>Escalated questions</strong>
                <p>Questions the AI could not answer confidently.</p>
              </div>
              <span className="hd-admin-attention-value">{pendingEscalations}</span>
              <span className="hd-admin-chevron">→</span>
            </Link>

            <Link to="/admin/review" className="hd-admin-attention-item">
              <span className="hd-admin-attention-icon hd-tone-green">
                <DashboardIcon name="review" />
              </span>
              <div>
                <strong>Answer review workflow</strong>
                <p>Validate approved human knowledge before reuse.</p>
              </div>
              <span className="hd-admin-attention-status">Review</span>
              <span className="hd-admin-chevron">→</span>
            </Link>

            <Link to="/admin/security" className="hd-admin-attention-item">
              <span className="hd-admin-attention-icon hd-tone-red">
                <DashboardIcon name="shield" />
              </span>
              <div>
                <strong>Security & audit</strong>
                <p>Review authentication activity and system events.</p>
              </div>
              <span className="hd-admin-attention-status">Monitor</span>
              <span className="hd-admin-chevron">→</span>
            </Link>
          </div>
        </article>

        <article className="hd-admin-panel hd-admin-notification-panel">
          <div className="hd-admin-panel-heading">
            <div>
              <span className="hd-admin-panel-overline">Latest updates</span>
              <h3>Notifications</h3>
            </div>
            <span className="hd-admin-panel-count hd-admin-panel-count-soft">
              {unreadNotifications}
            </span>
          </div>

          {loading ? (
            <div className="hd-admin-skeleton-list" aria-label="Loading notifications">
              <span />
              <span />
              <span />
            </div>
          ) : notifications.length === 0 ? (
            <div className="hd-admin-empty-state">
              <span className="hd-admin-empty-icon"><DashboardIcon name="bell" /></span>
              <strong>Nothing new right now</strong>
              <p>Recent workflow updates will appear here.</p>
            </div>
          ) : (
            <div className="hd-admin-notification-list">
              {notifications.slice(0, 3).map((item) => (
                <div key={item.id} className="hd-admin-notification-item">
                  <span className="hd-admin-notification-dot" aria-hidden="true" />
                  <div>
                    <strong>{item.title}</strong>
                    <p>{item.detail || item.message || 'System notification'}</p>
                  </div>
                </div>
              ))}
            </div>
          )}
        </article>
      </section>

      <section className="hd-admin-workspace-section">
        <div className="hd-admin-section-heading">
          <div>
            <span className="hd-admin-overline">Management workspace</span>
            <h2>Tools & governance</h2>
            <p>Open the area you need without searching through the sidebar.</p>
          </div>
        </div>

        <div className="hd-admin-module-grid">
          {MANAGEMENT_MODULES.map((module) => (
            <Link
              key={module.title}
              to={module.route}
              className={`hd-admin-module-card hd-tone-${module.tone}`}
            >
              <div className="hd-admin-module-top">
                <span className="hd-admin-module-icon">
                  <DashboardIcon name={module.icon} />
                </span>
                <span className="hd-admin-module-arrow">↗</span>
              </div>
              <span className="hd-admin-module-label">{module.label}</span>
              <h3>{module.title}</h3>
              <p>{module.description}</p>
            </Link>
          ))}
        </div>
      </section>

      <section className="hd-admin-panel hd-admin-activity-panel">
        <div className="hd-admin-panel-heading">
          <div>
            <span className="hd-admin-panel-overline">Audit trail</span>
            <h3>Recent system activity</h3>
          </div>
          <Link to="/admin/security" className="hd-admin-inline-link">
            View security log <span>→</span>
          </Link>
        </div>

        {loading ? (
          <div className="hd-admin-skeleton-list" aria-label="Loading activity">
            <span />
            <span />
            <span />
          </div>
        ) : activities.length === 0 ? (
          <div className="hd-admin-empty-state hd-admin-empty-state-inline">
            <strong>No recent activity</strong>
            <p>Audit actions will appear here as the system is used.</p>
          </div>
        ) : (
          <div className="hd-admin-activity-list">
            {activities.slice(0, 4).map((item, index) => (
              <div key={`${item.action}-${index}`} className="hd-admin-activity-item">
                <span className="hd-admin-activity-marker" aria-hidden="true" />
                <div>
                  <strong>{item.action}</strong>
                  {item.created_at ? (
                    <time dateTime={item.created_at}>{formatDateTime(item.created_at)}</time>
                  ) : null}
                </div>
              </div>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}
