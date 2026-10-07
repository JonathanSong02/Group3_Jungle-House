import { useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { useAuth } from '../../context/AuthContext';
import api from '../../services/api';
import { useLanguage } from '../../i18n/LanguageContext';
import { translateAuditAction } from '../../i18n/auditText';
import { translateNotificationTitle, translateNotificationDetail } from '../../i18n/notificationText';
import './styles/AdminDashboard.css';

const QUICK_ACTIONS = [
  { titleKey: 'adm.quick.users', route: '/admin/users', icon: 'users' },
  { titleKey: 'adm.quick.content', route: '/admin/content', icon: 'knowledge' },
  { titleKey: 'adm.quick.reviews', route: '/admin/review', icon: 'review' },
  { titleKey: 'adm.quick.quiz', route: '/admin/quiz-management', icon: 'quiz' },
  { titleKey: 'adm.quick.ai', route: '/admin/ai-settings', icon: 'settings' },
  { titleKey: 'adm.quick.notion', route: '/admin/notion-sync', icon: 'sync' },
];

function DashboardIcon({ name, size = 22 }) {
  const commonProps = {
    width: size,
    height: size,
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

    case 'arrow':
      return (
        <svg {...commonProps}>
          <path d="M5 12h14" />
          <path d="m14 7 5 5-5 5" />
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

function formatDateTime(value, locale) {
  if (!value) return '';
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? String(value) : date.toLocaleString(locale);
}

function parsePercent(value) {
  const parsed = Number.parseFloat(String(value || '').replace('%', ''));
  if (!Number.isFinite(parsed)) return 0;
  return Math.min(100, Math.max(0, parsed));
}

export default function AdminDashboard() {
  const { user } = useAuth();
  const { t, tOr, locale } = useLanguage();

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
        setUsers(Array.isArray(usersResponse.data) ? usersResponse.data : []);
      } catch (requestError) {
        if (cancelled) return;

        console.error('Admin dashboard fetch error:', requestError);
        setError(
          requestError.response?.data?.message ||
            requestError.response?.data?.error ||
            t('adm.unavailable')
        );
      } finally {
        if (!cancelled) setLoading(false);
      }
    };

    loadDashboard();

    return () => {
      cancelled = true;
    };
  }, [t]);

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
  const managerRoleRaw = String(user?.role || 'Manager').replace(/[_-]/g, ' ');
  const managerRole = tOr(`role.${managerRoleRaw.toLowerCase().replace(/\s/g, '')}`, managerRoleRaw);
  const attentionCount = pendingUsers + pendingEscalations;

  const overviewCards = [
    {
      label: t('adm.users'),
      value: totalUsers,
      route: '/admin/users',
      icon: 'users',
      tone: 'blue',
      helper: pendingUsers > 0 ? t('adm.helper.pendingN', { n: pendingUsers }) : t('adm.helper.allAccounts'),
    },
    {
      label: t('adm.pending'),
      value: pendingUsers,
      route: '/admin/users',
      icon: 'review',
      tone: pendingUsers > 0 ? 'amber' : 'green',
      helper: pendingUsers > 0 ? t('adm.helper.needsReview') : t('adm.helper.upToDate'),
    },
    {
      label: t('adm.articles'),
      value: articles,
      route: '/admin/content',
      icon: 'knowledge',
      tone: 'green',
      helper: t('adm.helper.kb'),
    },
    {
      label: t('adm.escalations'),
      value: pendingEscalations,
      route: '/escalation',
      icon: 'question',
      tone: pendingEscalations > 0 ? 'amber' : 'slate',
      helper: pendingEscalations > 0 ? t('adm.helper.needsAction') : t('adm.helper.clear'),
    },
  ];

  return (
    <div className="hd-admin-page" aria-busy={loading}>
      <header className="hd-admin-hero">
        <div className="hd-admin-hero-copy">
          <div className="hd-admin-hero-kicker">
            <span className="hd-admin-live-dot" aria-hidden="true" />
            {t('adm.workspace')}
          </div>
          <h1>{t('adm.welcome', { name: managerName })}</h1>
          <p>{t('adm.welcomeSub')}</p>

          <div className="hd-admin-hero-meta" aria-label={t('adm.accountStatusAria')}>
            <span className="hd-admin-role-chip">{managerRole}</span>
            <span className={`hd-admin-attention-chip ${attentionCount > 0 ? 'is-active' : ''}`}>
              {loading ? t('adm.checking') : attentionCount > 0 ? t('adm.needAttention', { n: attentionCount }) : t('adm.allGood')}
            </span>
          </div>
        </div>

        <div className="hd-admin-header-actions">
          <Link to="/chat" className="hd-admin-btn hd-admin-btn-secondary">
            <DashboardIcon name="question" size={19} />
            {t('adm.askAi')}
          </Link>

          <Link to="/admin/content/add" className="hd-admin-btn hd-admin-btn-primary">
            <span className="hd-admin-btn-plus" aria-hidden="true">+</span>
            {t('adm.addArticle')}
          </Link>
        </div>
      </header>

      {error ? (
        <div className="hd-admin-data-notice" role="status">
          <DashboardIcon name="bell" size={18} />
          <span>{error}</span>
        </div>
      ) : null}

      <section className="hd-admin-overview-grid" aria-label={t('adm.overviewAria')}>
        {overviewCards.map((item) => (
          <Link
            key={item.label}
            to={item.route}
            className={`hd-admin-metric hd-tone-${item.tone}`}
          >
            <div className="hd-admin-metric-head">
              <span className="hd-admin-metric-icon">
                <DashboardIcon name={item.icon} size={20} />
              </span>
              <span className="hd-admin-metric-label">{item.label}</span>
            </div>

            <div className="hd-admin-metric-body">
              <strong>{loading ? '—' : item.value}</strong>
              <span>{loading ? t('adm.loading') : item.helper}</span>
            </div>

            <span className="hd-admin-card-arrow" aria-hidden="true">
              <DashboardIcon name="arrow" size={18} />
            </span>
          </Link>
        ))}
      </section>

      <section className="hd-admin-command-grid">
        <article className="hd-admin-command-panel">
          <div className="hd-admin-section-heading">
            <div>
              <span className="hd-admin-section-kicker">{t('adm.management')}</span>
              <h2>{t('adm.quickActions')}</h2>
            </div>
          </div>

          <div className="hd-admin-quick-grid">
            {QUICK_ACTIONS.map((item) => (
              <Link key={item.titleKey} to={item.route} className="hd-admin-quick-card">
                <span className="hd-admin-quick-icon">
                  <DashboardIcon name={item.icon} size={20} />
                </span>
                <strong>{t(item.titleKey)}</strong>
                <span className="hd-admin-quick-arrow" aria-hidden="true">
                  <DashboardIcon name="arrow" size={17} />
                </span>
              </Link>
            ))}
          </div>
        </article>

        <aside className="hd-admin-health-panel" aria-label={t('adm.pulseAria')}>
          <div className="hd-admin-section-heading hd-admin-section-heading-tight">
            <div>
              <span className="hd-admin-section-kicker">{t('adm.system')}</span>
              <h2>{t('adm.pulse')}</h2>
            </div>
            <Link to="/admin/analytics" className="hd-admin-inline-link">{t('adm.analytics')}</Link>
          </div>

          <div className="hd-admin-health-list">
            <div className="hd-admin-health-item hd-admin-health-item-ai">
              <div>
                <span>{t('adm.aiConfidence')}</span>
                <strong>{loading ? '—' : ai.accuracy || '0%'}</strong>
              </div>
              <div className="hd-admin-confidence-ring" style={{ '--confidence': `${confidence * 3.6}deg` }} aria-hidden="true">
                <span>{loading ? '—' : `${Math.round(confidence)}%`}</span>
              </div>
            </div>

            <div className="hd-admin-health-item">
              <span>{t('adm.questionsWeek')}</span>
              <strong>{loading ? '—' : weeklyQuestions}</strong>
            </div>

            <div className="hd-admin-health-item">
              <span>{t('adm.unreadNotif')}</span>
              <strong>{loading ? '—' : unreadNotifications}</strong>
            </div>
          </div>
        </aside>
      </section>

      <section className="hd-admin-info-grid">
        <article className="hd-admin-panel">
          <div className="hd-admin-panel-heading">
            <div>
              <span className="hd-admin-section-kicker">{t('adm.latest')}</span>
              <h3>{t('adm.recentActivity')}</h3>
            </div>
            <Link to="/admin/security" className="hd-admin-inline-link">{t('adm.viewAll')}</Link>
          </div>

          {loading ? (
            <div className="hd-admin-skeleton-list" aria-hidden="true">
              <span />
              <span />
              <span />
            </div>
          ) : activities.length === 0 ? (
            <div className="hd-admin-empty-state">
              <span className="hd-admin-empty-icon"><DashboardIcon name="shield" size={20} /></span>
              <strong>{t('adm.noActivity')}</strong>
              <p>{t('adm.noActivityHint')}</p>
            </div>
          ) : (
            <div className="hd-admin-activity-list">
              {activities.slice(0, 4).map((item, index) => (
                <div key={`${item.action}-${index}`} className="hd-admin-activity-item">
                  <span className="hd-admin-activity-marker" aria-hidden="true" />
                  <div>
                    <strong>{translateAuditAction(t, item.action)}</strong>
                    {item.created_at ? (
                      <time dateTime={item.created_at}>{formatDateTime(item.created_at, locale)}</time>
                    ) : null}
                  </div>
                </div>
              ))}
            </div>
          )}
        </article>

        <article className="hd-admin-panel">
          <div className="hd-admin-panel-heading">
            <div>
              <span className="hd-admin-section-kicker">{t('adm.inbox')}</span>
              <h3>{t('adm.notifications')}</h3>
            </div>
            <span className="hd-admin-panel-count">{loading ? '—' : unreadNotifications}</span>
          </div>

          {loading ? (
            <div className="hd-admin-skeleton-list" aria-hidden="true">
              <span />
              <span />
              <span />
            </div>
          ) : notifications.length === 0 ? (
            <div className="hd-admin-empty-state">
              <span className="hd-admin-empty-icon"><DashboardIcon name="bell" size={20} /></span>
              <strong>{t('adm.caughtUp')}</strong>
              <p>{t('adm.caughtUpHint')}</p>
            </div>
          ) : (
            <div className="hd-admin-notification-list">
              {notifications.slice(0, 4).map((item, index) => (
                <div key={item.id ?? `${item.title}-${index}`} className="hd-admin-notification-item">
                  <span className="hd-admin-notification-dot" aria-hidden="true" />
                  <div>
                    <strong>{translateNotificationTitle(t, item.title)}</strong>
                    <p>{translateNotificationDetail(t, item.detail || item.message || t('adm.systemUpdate'))}</p>
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
