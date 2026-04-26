import { NavLink } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';

function linkClass({ isActive }) {
  return isActive ? 'sidebar-link active' : 'sidebar-link';
}

export default function Sidebar() {
  const { user } = useAuth();
  const role = user?.role;

  return (
    <aside className="sidebar">
      <div className="sidebar-brand">
        <p className="eyebrow">Jungle House</p>
        <h2 className="sidebar-title">AI Wiki</h2>
        <p className="sidebar-subtitle">Training & Knowledge Hub</p>
      </div>

      <nav className="sidebar-nav">
        {(role === 'staff' || role === 'teamlead') && (
          <>
            <div className="sidebar-section-label">Staff Workspace</div>
            <NavLink className={linkClass} to="/dashboard">Dashboard</NavLink>
            <NavLink className={linkClass} to="/chat">AI Chat</NavLink>
            <NavLink className={linkClass} to="/knowledge">Knowledge Base</NavLink>
            <NavLink className={linkClass} to="/notifications">Notifications</NavLink>
            <NavLink className={linkClass} to="/quiz">Quiz / Training</NavLink>
          </>
        )}

        {role === 'manager' && (
          <>
            <div className="sidebar-section-label">Admin Workspace</div>
            <NavLink className={linkClass} to="/admin/dashboard">Admin Dashboard</NavLink>
            <NavLink className={linkClass} to="/admin/content">Content Management</NavLink>
            <NavLink className={linkClass} to="/admin/review">Review Management</NavLink>
            <NavLink className={linkClass} to="/admin/users">User Management</NavLink>
            <NavLink className={linkClass} to="/admin/ai-settings">AI Settings</NavLink>
            <NavLink className={linkClass} to="/admin/analytics">Analytics</NavLink>
            <NavLink className={linkClass} to="/admin/security">Security / Monitoring</NavLink>
          </>
        )}

        {(role === 'teamlead' || role === 'manager') && (
          <>
            <div className="sidebar-section-label">Review</div>
            <NavLink className={linkClass} to="/escalation">Escalation</NavLink>
          </>
        )}

        <div className="sidebar-section-label">Account</div>
        <NavLink className={linkClass} to="/profile">Profile</NavLink>
      </nav>
    </aside>
  );
}