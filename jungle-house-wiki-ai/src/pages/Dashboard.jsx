import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom"; // 1. Import useNavigate
import PageHeader from "../components/PageHeader";

export default function Dashboard() {
  const [stats, setStats] = useState([]);
  const [notifications, setNotifications] = useState([]);
  const [activities, setActivities] = useState([]);
  const [ai, setAi] = useState({ accuracy: "0%" });

  const navigate = useNavigate(); // 2. Initialize the hook

  useEffect(() => {
    fetch("http://127.0.0.1:5000/api/dashboard")
      .then((res) => res.json())
      .then((data) => {
        setStats(data.stats || []);
        setNotifications(data.notifications || []);
        setActivities(data.activities || []);
        setAi(data.ai || {});
      });
  }, []);

  return (
    <div>
      <PageHeader
        title="Dashboard"
        subtitle="Quick access to AI chat, knowledge, alerts, and training updates."
      />

      {/* 📊 Stats */}
      <div className="stats-grid">
        {stats.map((item) => (
          <article key={item.label} className="card-like stat-card">
            <p className="muted small">{item.label}</p>
            <h3>{item.value}</h3>
          </article>
        ))}
      </div>

      {/* 🤖 AI Insight */}
      <div className="stats-grid">
        <article className="card-like stat-card">
          <p className="muted small">AI Accuracy</p>
          <h3>{ai.accuracy}</h3>
        </article>
      </div>

      {/* ⚠️ Escalation Alert */}
      {stats.find(s => s.label === "Pending Escalations")?.value > 0 && (
        <div className="alert-card">
          ⚠️ You have pending escalations that require attention
        </div>
      )}

      <div className="two-column-grid">
        {/* 📢 Announcements */}
        <section className="card-like">
          <h3>Recent Notifications</h3>
          <ul className="simple-list">
            {notifications.map((n, i) => (
              <li key={i}>{n.message}</li>
            ))}
          </ul>
        </section>

        {/* 📌 Activity */}
        <section className="card-like">
          <h3>Recent Activity</h3>
          <ul className="simple-list">
            {activities.map((a, i) => (
              <li key={i}>{a.action}</li>
            ))}
          </ul>
        </section>
      </div>

      {/* 🚀 Quick Actions */}
      <div className="card-like">
        <h3>Quick Actions</h3>
        <div className="action-buttons">
          {/* 3. Update all buttons to use navigate() and the correct paths */}
          <button onClick={() => navigate("/chat")}>
            Ask AI
          </button>
          <button onClick={() => navigate("/knowledge")}>
            Browse Knowledge
          </button>
          <button onClick={() => navigate("/quiz")}>
            Start Training
          </button>
        </div>
      </div>
    </div>
  );
}