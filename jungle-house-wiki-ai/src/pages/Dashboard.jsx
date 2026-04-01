import PageHeader from '../components/PageHeader';
import { announcements, dashboardStats } from '../data/mockData';

export default function Dashboard() {
  return (
    <div>
      <PageHeader
        title="Dashboard"
        subtitle="Quick access to AI chat, knowledge, alerts, and training updates."
      />

      <div className="stats-grid">
        {dashboardStats.map((item) => (
          <article key={item.label} className="card-like stat-card">
            <p className="muted small">{item.label}</p>
            <h3>{item.value}</h3>
          </article>
        ))}
      </div>

      <div className="two-column-grid">
        <section className="card-like">
          <h3>Notice / Announcement</h3>
          <ul className="simple-list">
            {announcements.map((notice) => (
              <li key={notice}>{notice}</li>
            ))}
          </ul>
        </section>

        <section className="card-like">
          <h3>Suggested next actions</h3>
          <ul className="simple-list">
            <li>Open AI Chat to test question flow.</li>
            <li>Browse knowledge articles and check category layout.</li>
            <li>Review escalation flow for low-confidence answers.</li>
            <li>Validate sidebar visibility for each role.</li>
          </ul>
        </section>
      </div>
    </div>
  );
}
