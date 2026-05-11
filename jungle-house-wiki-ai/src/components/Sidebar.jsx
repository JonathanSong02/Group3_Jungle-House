import { useEffect, useRef, useState } from 'react';
import { NavLink, useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';

function linkClass({ isActive }) {
  return isActive ? 'sidebar-link active' : 'sidebar-link';
}

export default function Sidebar() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const role = user?.role;

  const [isCollapsed, setIsCollapsed] = useState(false);
  const [isUserMenuOpen, setIsUserMenuOpen] = useState(false);
  const userMenuRef = useRef(null);

  useEffect(() => {
    document.body.classList.toggle('sidebar-is-collapsed', isCollapsed);

    return () => {
      document.body.classList.remove('sidebar-is-collapsed');
    };
  }, [isCollapsed]);

  useEffect(() => {
    const handleClickOutside = (event) => {
      if (userMenuRef.current && !userMenuRef.current.contains(event.target)) {
        setIsUserMenuOpen(false);
      }
    };

    document.addEventListener('mousedown', handleClickOutside);

    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
    };
  }, []);

  const handleLogout = () => {
    logout();
    navigate('/login');
  };

  const getInitial = () => {
    const name = user?.name || user?.email || 'U';
    return name.charAt(0).toUpperCase();
  };

  const closeMobileAfterClick = () => {
    setIsUserMenuOpen(false);
  };

  const handleToggleSidebar = () => {
    setIsCollapsed((prev) => !prev);
    setIsUserMenuOpen(false);
  };

  return (
    <aside className={`sidebar modern-sidebar ${isCollapsed ? 'collapsed' : ''}`}>
      <div className="sidebar-inner">
        <div className="sidebar-main">
          <div className="sidebar-brand">
            <div className="sidebar-brand-top">
              <div className="sidebar-logo-wrap">
                <div className="sidebar-logo">JH</div>

                <div className="sidebar-brand-text">
                  <p className="eyebrow">Jungle House</p>
                  <h2 className="sidebar-title">AI Wiki</h2>
                  <p className="sidebar-subtitle">Training & Knowledge Hub</p>
                </div>
              </div>

              <button
                type="button"
                className="sidebar-toggle-btn desktop-toggle"
                onClick={handleToggleSidebar}
                aria-label={isCollapsed ? 'Open sidebar' : 'Close sidebar'}
              >
                {isCollapsed ? '›' : '‹'}
              </button>
            </div>
          </div>

          <nav className="sidebar-nav">
            {(role === 'staff' || role === 'teamlead') && (
              <>
                <div className="sidebar-section-label">Staff Workspace</div>

                <NavLink className={linkClass} to="/dashboard" onClick={closeMobileAfterClick}>
                  <span className="sidebar-icon">▦</span>
                  <span className="sidebar-link-text">Dashboard</span>
                </NavLink>

                <NavLink className={linkClass} to="/chat" onClick={closeMobileAfterClick}>
                  <span className="sidebar-icon">✦</span>
                  <span className="sidebar-link-text">AI Chat</span>
                </NavLink>

                <NavLink className={linkClass} to="/knowledge" onClick={closeMobileAfterClick}>
                  <span className="sidebar-icon">□</span>
                  <span className="sidebar-link-text">Knowledge Base</span>
                </NavLink>

                <NavLink className={linkClass} to="/messages" onClick={closeMobileAfterClick}>
                  <span className="sidebar-icon">✉</span>
                  <span className="sidebar-link-text">Messages</span>
                </NavLink>

                <NavLink className={linkClass} to="/notifications" onClick={closeMobileAfterClick}>
                  <span className="sidebar-icon">●</span>
                  <span className="sidebar-link-text">Notifications</span>
                </NavLink>

                <NavLink className={linkClass} to="/quiz" onClick={closeMobileAfterClick}>
                  <span className="sidebar-icon">✓</span>
                  <span className="sidebar-link-text">Quiz / Training</span>
                </NavLink>
              </>
            )}

            {role === 'manager' && (
              <>
                <div className="sidebar-section-label">Admin Workspace</div>

                <NavLink className={linkClass} to="/admin/dashboard" onClick={closeMobileAfterClick}>
                  <span className="sidebar-icon">▦</span>
                  <span className="sidebar-link-text">Admin Dashboard</span>
                </NavLink>

                <NavLink className={linkClass} to="/admin/content" onClick={closeMobileAfterClick}>
                  <span className="sidebar-icon">□</span>
                  <span className="sidebar-link-text">Content Management</span>
                </NavLink>

                <NavLink
                  className={linkClass}
                  to="/admin/quiz-management"
                  onClick={closeMobileAfterClick}
                >
                  <span className="sidebar-icon">✓</span>
                  <span className="sidebar-link-text">Quiz Management</span>
                </NavLink>

                <NavLink className={linkClass} to="/messages" onClick={closeMobileAfterClick}>
                  <span className="sidebar-icon">✉</span>
                  <span className="sidebar-link-text">Messages</span>
                </NavLink>

                <NavLink className={linkClass} to="/admin/review" onClick={closeMobileAfterClick}>
                  <span className="sidebar-icon">◇</span>
                  <span className="sidebar-link-text">Review Management</span>
                </NavLink>

                <NavLink className={linkClass} to="/admin/users" onClick={closeMobileAfterClick}>
                  <span className="sidebar-icon">♙</span>
                  <span className="sidebar-link-text">User Management</span>
                </NavLink>

                <NavLink className={linkClass} to="/admin/ai-settings" onClick={closeMobileAfterClick}>
                  <span className="sidebar-icon">⚙</span>
                  <span className="sidebar-link-text">AI Settings</span>
                </NavLink>

                <NavLink className={linkClass} to="/admin/analytics" onClick={closeMobileAfterClick}>
                  <span className="sidebar-icon">↗</span>
                  <span className="sidebar-link-text">Analytics</span>
                </NavLink>

                <NavLink className={linkClass} to="/admin/security" onClick={closeMobileAfterClick}>
                  <span className="sidebar-icon">◈</span>
                  <span className="sidebar-link-text">Security / Monitoring</span>
                </NavLink>
              </>
            )}

            {(role === 'teamlead' || role === 'manager') && (
              <>
                <div className="sidebar-section-label">Review</div>

                <NavLink className={linkClass} to="/escalation" onClick={closeMobileAfterClick}>
                  <span className="sidebar-icon">!</span>
                  <span className="sidebar-link-text">Escalation</span>
                </NavLink>
              </>
            )}

            <div className="sidebar-section-label">Account</div>

            <NavLink className={linkClass} to="/profile" onClick={closeMobileAfterClick}>
              <span className="sidebar-icon">○</span>
              <span className="sidebar-link-text">Profile</span>
            </NavLink>
          </nav>
        </div>

        <div
          ref={userMenuRef}
          className={`sidebar-user-card ${isUserMenuOpen ? 'menu-open' : ''}`}
        >
          <button
            type="button"
            className="sidebar-user-main"
            onClick={() => setIsUserMenuOpen((prev) => !prev)}
            aria-label="Open user menu"
            aria-expanded={isUserMenuOpen}
          >
            <span className="sidebar-user-avatar sidebar-user-toggle">{getInitial()}</span>

            <span className="sidebar-user-info">
              <strong>{user?.name || 'User'}</strong>
              <span>{user?.role || 'Staff'}</span>
            </span>

            <span className="sidebar-user-arrow">›</span>
          </button>

          {isUserMenuOpen ? (
            <div className="sidebar-user-menu">
              <div className="sidebar-user-menu-header">
                <span className="sidebar-user-avatar small-avatar">{getInitial()}</span>

                <div>
                  <strong>{user?.name || 'User'}</strong>
                  <span>{user?.role || 'Staff'}</span>
                </div>
              </div>

              <div className="sidebar-user-menu-divider" />

              <NavLink
                to="/profile"
                className="sidebar-user-menu-item"
                onClick={() => setIsUserMenuOpen(false)}
              >
                <span>○</span>
                <strong>Profile</strong>
              </NavLink>

              <button
                type="button"
                className="sidebar-user-menu-item"
                onClick={handleLogout}
              >
                <span>↪</span>
                <strong>Log out</strong>
              </button>
            </div>
          ) : null}
        </div>
      </div>
    </aside>
  );
}