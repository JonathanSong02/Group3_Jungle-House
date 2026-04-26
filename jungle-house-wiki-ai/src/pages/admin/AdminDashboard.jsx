import { Link } from 'react-router-dom';
import PageHeader from '../../components/PageHeader';

export default function AdminDashboard() {
  return (
    <div>
      <PageHeader
        title="Admin Dashboard"
        subtitle="Manage Jungle House AI Wiki content, users, reviews, and system monitoring."
      />

      <section className="admin-hero-card card-like">
        <div>
          <p className="eyebrow">Manager Workspace</p>
          <h2>Jungle House AI Wiki Control Centre</h2>
          <p className="muted">
            Use this dashboard to control knowledge content, review escalated answers,
            manage staff accounts, and monitor AI performance.
          </p>
        </div>

        <Link to="/admin/content/add" className="primary-btn link-btn">
          + Add New Article
        </Link>
      </section>

      <section className="admin-dashboard-grid top-gap">
        <Link to="/admin/content" className="card-like admin-action-card">
          <p className="eyebrow">Knowledge</p>
          <h3>Content Management</h3>
          <p className="muted">Create, edit, and organize SOP, product, and sales articles.</p>
        </Link>

        <Link to="/admin/review" className="card-like admin-action-card">
          <p className="eyebrow">Review</p>
          <h3>Review Management</h3>
          <p className="muted">Review submitted answers before publishing to the knowledge base.</p>
        </Link>

        <Link to="/admin/users" className="card-like admin-action-card">
          <p className="eyebrow">Users</p>
          <h3>User Management</h3>
          <p className="muted">Activate accounts and change staff or team lead roles.</p>
        </Link>

        <Link to="/escalation" className="card-like admin-action-card">
          <p className="eyebrow">Escalation</p>
          <h3>Escalated Questions</h3>
          <p className="muted">Handle low-confidence AI questions that need human review.</p>
        </Link>

        <Link to="/admin/ai-settings" className="card-like admin-action-card">
          <p className="eyebrow">AI</p>
          <h3>AI Settings</h3>
          <p className="muted">Adjust confidence threshold and AI behaviour settings.</p>
        </Link>

        <Link to="/admin/security" className="card-like admin-action-card">
          <p className="eyebrow">Security</p>
          <h3>Security Monitoring</h3>
          <p className="muted">Check login activity and monitor system access.</p>
        </Link>
      </section>
    </div>
  );
}