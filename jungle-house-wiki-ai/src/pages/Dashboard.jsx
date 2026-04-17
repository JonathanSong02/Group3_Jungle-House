import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import PageHeader from '../components/PageHeader';

export default function Dashboard() {
  const navigate = useNavigate();

  const [stats, setStats] = useState([]);
  const [notifications, setNotifications] = useState([]);
  const [activities, setActivities] = useState([]);
  const [ai, setAi] = useState({ accuracy: '0%' });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    const fetchDashboard = async () => {
      try {
        setLoading(true);
        setError('');

        const response = await fetch('http://127.0.0.1:5000/api/dashboard');
        const data = await response.json();

        if (!response.ok) {
          throw new Error(data.error || 'Failed to load dashboard.');
        }

        setStats(data.stats || []);
        setNotifications(data.notifications || []);
        setActivities(data.activities || []);
        setAi(data.ai || { accuracy: '0%' });
      } catch (err) {
        setError(err.message || 'Unable to load dashboard.');
      } finally {
        setLoading(false);
      }
    };

    fetchDashboard();
  }, []);

  const pendingEscalations =
    stats.find((item) => item.label === 'Pending Escalations')?.value || 0;

  return (
    <div>
      <PageHeader
        title="Dashboard"
        subtitle="Quick access to AI chat, knowledge, alerts, and training updates."
      />

      {loading ? <p className="muted">Loading dashboard...</p> : null}
      {error ? <p className="error-text">{error}</p> : null}

      {!loading && !error ? (
        <>
          <div className="stats-grid">
            {stats.map((item) => (
              <article key={item.label} className="card-like stat-card">
                <p className="muted small">{item.label}</p>
                <h3>{item.value}</h3>
              </article>
            ))}

            <article className="card-like stat-card">
              <p className="muted small">AI Accuracy</p>
              <h3>{ai.accuracy}</h3>
            </article>
          </div>

          {pendingEscalations > 0 ? (
            <div className="alert-card">
              ⚠️ You have {pendingEscalations} pending escalation
              {pendingEscalations > 1 ? 's' : ''} requiring attention.
            </div>
          ) : null}

          <div className="card-like">
            <h3>Quick Actions</h3>
            <div className="action-buttons">
              <button className="primary-btn" onClick={() => navigate('/ai-chat')}>
                Ask AI
              </button>
              <button className="secondary-btn" onClick={() => navigate('/knowledge')}>
                Browse Knowledge
              </button>
              <button className="secondary-btn" onClick={() => navigate('/notifications')}>
                View Notifications
              </button>
            </div>
          </div>

          <div className="two-column-grid">
            <section className="card-like">
              <h3>Recent Notifications</h3>
              {notifications.length === 0 ? (
                <p className="muted">No recent notifications.</p>
              ) : (
                <ul className="simple-list">
                  {notifications.map((item) => (
                    <li key={item.id}>
                      <strong>{item.title}</strong>
                      <br />
                      <span className="muted">{item.message}</span>
                    </li>
                  ))}
                </ul>
              )}
            </section>

            <section className="card-like">
              <h3>Recent Activity</h3>
              {activities.length === 0 ? (
                <p className="muted">No recent activity.</p>
              ) : (
                <ul className="simple-list">
                  {activities.map((item, index) => (
                    <li key={`${item.action}-${index}`}>
                      <strong>{item.action}</strong>
                      {item.created_at ? (
                        <>
                          <br />
                          <span className="muted small">
                            {new Date(item.created_at).toLocaleString()}
                          </span>
                        </>
                      ) : null}
                    </li>
                  ))}
                </ul>
              )}
            </section>
          </div>
        </>
      ) : null}
    </div>
  );
}