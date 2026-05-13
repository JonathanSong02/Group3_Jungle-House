import { useEffect, useRef, useState } from 'react';
import { NavLink, useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';

function linkClass({ isActive }) {
  return isActive ? 'sidebar-link active' : 'sidebar-link';
}

function Icon({ name }) {
  const iconProps = {
    viewBox: '0 0 24 24',
    fill: 'none',
    stroke: 'currentColor',
    strokeWidth: '2.2',
    strokeLinecap: 'round',
    strokeLinejoin: 'round',
    'aria-hidden': 'true',
  };

  const icons = {
    menu: (
      <svg {...iconProps}>
        <path d="M4 7h16" />
        <path d="M4 12h16" />
        <path d="M4 17h16" />
      </svg>
    ),
    dashboard: (
      <svg {...iconProps}>
        <path d="M4 4h7v7H4z" />
        <path d="M13 4h7v5h-7z" />
        <path d="M13 11h7v9h-7z" />
        <path d="M4 13h7v7H4z" />
      </svg>
    ),
    chat: (
      <svg {...iconProps}>
        <path d="M5 6.5A4.5 4.5 0 0 1 9.5 2h5A4.5 4.5 0 0 1 19 6.5v4A4.5 4.5 0 0 1 14.5 15H11l-4.2 4.2c-.5.5-1.3.15-1.3-.55V15A4.5 4.5 0 0 1 5 10.5z" />
        <path d="M9 7.5h6" />
        <path d="M9 11h4" />
      </svg>
    ),
    knowledge: (
      <svg {...iconProps}>
        <path d="M5 4.5A2.5 2.5 0 0 1 7.5 2H19v17H7.5A2.5 2.5 0 0 0 5 21.5z" />
        <path d="M5 4.5v17" />
        <path d="M9 6h6" />
        <path d="M9 10h6" />
      </svg>
    ),
    messages: (
      <svg {...iconProps}>
        <path d="M4 6h16v12H4z" />
        <path d="m4 7 8 6 8-6" />
      </svg>
    ),
    notifications: (
      <svg {...iconProps}>
        <path d="M18 9a6 6 0 0 0-12 0c0 7-3 7-3 7h18s-3 0-3-7" />
        <path d="M10 20a2 2 0 0 0 4 0" />
      </svg>
    ),
    quiz: (
      <svg {...iconProps}>
        <path d="M8 4h8" />
        <path d="M9 2h6v4H9z" />
        <path d="M6 5h12v16H6z" />
        <path d="m9 12 2 2 4-4" />
        <path d="M9 17h6" />
      </svg>
    ),
    content: (
      <svg {...iconProps}>
        <path d="M4 5h16" />
        <path d="M4 12h16" />
        <path d="M4 19h16" />
        <path d="M8 5v14" />
      </svg>
    ),
    review: (
      <svg {...iconProps}>
        <path d="M12 3 20 7v6c0 5-3.5 7.5-8 8-4.5-.5-8-3-8-8V7z" />
        <path d="m8.5 12 2.3 2.3 4.7-5" />
      </svg>
    ),
    users: (
      <svg {...iconProps}>
        <path d="M16 21v-2a4 4 0 0 0-4-4H7a4 4 0 0 0-4 4v2" />
        <path d="M9.5 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8" />
        <path d="M22 21v-2a4 4 0 0 0-3-3.9" />
        <path d="M16 3.3a4 4 0 0 1 0 7.4" />
      </svg>
    ),
    settings: (
      <svg {...iconProps}>
        <path d="M12 15.5A3.5 3.5 0 1 0 12 8a3.5 3.5 0 0 0 0 7.5" />
        <path d="M19.4 15a1.7 1.7 0 0 0 .34 1.88l.06.06a2 2 0 0 1-2.83 2.83l-.06-.06A1.7 1.7 0 0 0 15 19.4a1.7 1.7 0 0 0-1 .6 1.7 1.7 0 0 0-.4 1.05V21a2 2 0 0 1-4 0v-.09A1.7 1.7 0 0 0 8.6 19.4a1.7 1.7 0 0 0-1.88.34l-.06.06a2 2 0 0 1-2.83-2.83l.06-.06A1.7 1.7 0 0 0 4.6 15a1.7 1.7 0 0 0-.6-1A1.7 1.7 0 0 0 2.95 13H3a2 2 0 0 1 0-4h-.05A1.7 1.7 0 0 0 4.6 8.6a1.7 1.7 0 0 0-.34-1.88l-.06-.06A2 2 0 0 1 7.03 3.83l.06.06A1.7 1.7 0 0 0 9 4.6a1.7 1.7 0 0 0 1-.6A1.7 1.7 0 0 0 10.4 2.95V3a2 2 0 0 1 4 0v-.05A1.7 1.7 0 0 0 15 4.6a1.7 1.7 0 0 0 1.88-.34l.06-.06a2 2 0 0 1 2.83 2.83l-.06.06A1.7 1.7 0 0 0 19.4 9a1.7 1.7 0 0 0 .6 1c.3.25.67.4 1.05.4H21a2 2 0 0 1 0 4h.05A1.7 1.7 0 0 0 19.4 15" />
      </svg>
    ),
    analytics: (
      <svg {...iconProps}>
        <path d="M4 19V5" />
        <path d="M4 19h16" />
        <path d="M8 16v-5" />
        <path d="M12 16V8" />
        <path d="M16 16v-3" />
        <path d="m16 8 4-4" />
        <path d="M16 4h4v4" />
      </svg>
    ),
    security: (
      <svg {...iconProps}>
        <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10" />
        <path d="M9.5 12.5 11.5 14.5 15 10" />
      </svg>
    ),
    escalation: (
      <svg {...iconProps}>
        <path d="M12 9v4" />
        <path d="M12 17h.01" />
        <path d="M10.3 3.9 2.5 17.3A2 2 0 0 0 4.2 20h15.6a2 2 0 0 0 1.7-2.7L13.7 3.9a2 2 0 0 0-3.4 0" />
      </svg>
    ),
    profile: (
      <svg {...iconProps}>
        <path d="M12 12a4 4 0 1 0 0-8 4 4 0 0 0 0 8" />
        <path d="M4 21a8 8 0 0 1 16 0" />
      </svg>
    ),
    logout: (
      <svg {...iconProps}>
        <path d="M10 17 15 12 10 7" />
        <path d="M15 12H3" />
        <path d="M21 19V5a2 2 0 0 0-2-2h-5" />
      </svg>
    ),
    chevronLeft: (
      <svg {...iconProps}>
        <path d="m15 18-6-6 6-6" />
      </svg>
    ),
    chevronRight: (
      <svg {...iconProps}>
        <path d="m9 18 6-6-6-6" />
      </svg>
    ),
  };

  return icons[name] || icons.dashboard;
}

function SidebarIcon({ name }) {
  return (
    <span className="sidebar-icon">
      <Icon name={name} />
    </span>
  );
}

function SidebarLogo() {
  return (
    <div className="sidebar-logo" aria-label="Jungle House AI Wiki logo">
      <svg viewBox="0 0 64 64" fill="none" aria-hidden="true">
        <path
          className="jh-logo-cell jh-logo-cell-main"
          d="M32 6 53 18v28L32 58 11 46V18z"
        />
        <path className="jh-logo-cell" d="M32 14 45 21.5v17L32 46 19 38.5v-17z" />
        <path className="jh-logo-leaf" d="M30 34c-8.5-1.2-12.8-6.8-12.8-14.3 8.6 0 14.2 4.2 15.7 12.8" />
        <path className="jh-logo-leaf" d="M34 34c8.5-1.2 12.8-6.8 12.8-14.3-8.6 0-14.2 4.2-15.7 12.8" />
        <circle className="jh-logo-dot" cx="32" cy="36" r="4.2" />
      </svg>
    </div>
  );
}

export default function Sidebar() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const role = user?.role;
  const normalizedRole = String(role || '').toLowerCase().replace(/[\s_-]/g, '');

  const isStaff = normalizedRole === 'staff';
  const isTeamLead = normalizedRole === 'teamlead';
  const isManager = normalizedRole === 'manager';

  const [isCollapsed, setIsCollapsed] = useState(false);
  const [isMobileOpen, setIsMobileOpen] = useState(false);
  const [isUserMenuOpen, setIsUserMenuOpen] = useState(false);
  const userMenuRef = useRef(null);

  useEffect(() => {
    document.body.classList.toggle('sidebar-is-collapsed', isCollapsed);
    document.body.classList.toggle('sidebar-mobile-open', isMobileOpen);

    return () => {
      document.body.classList.remove('sidebar-is-collapsed');
      document.body.classList.remove('sidebar-mobile-open');
    };
  }, [isCollapsed, isMobileOpen]);

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
    const name = user?.name || user?.full_name || user?.email || 'U';
    return String(name).charAt(0).toUpperCase();
  };

  const closeMobileAfterClick = () => {
    setIsUserMenuOpen(false);

    if (window.innerWidth <= 1024) {
      setIsMobileOpen(false);
    }
  };

  const handleToggleSidebar = () => {
    if (window.innerWidth <= 1024) {
      setIsMobileOpen((prev) => !prev);
      setIsUserMenuOpen(false);
      return;
    }

    setIsCollapsed((prev) => !prev);
    setIsUserMenuOpen(false);
  };

  return (
    <>
      <button
        type="button"
        className="mobile-sidebar-open-btn"
        onClick={() => setIsMobileOpen(true)}
        aria-label="Open sidebar"
      >
        <Icon name="menu" />
      </button>

      {isMobileOpen ? (
        <button
          type="button"
          className="mobile-sidebar-overlay"
          onClick={() => setIsMobileOpen(false)}
          aria-label="Close sidebar overlay"
        />
      ) : null}

      <aside className={`sidebar modern-sidebar ${isCollapsed ? 'collapsed' : ''}`}>
        <div className="sidebar-inner">
          <div className="sidebar-main">
            <div className="sidebar-brand">
              <div className="sidebar-brand-top">
                <div className="sidebar-logo-wrap">
                  <SidebarLogo />

                  <div className="sidebar-brand-text">
                    <p className="eyebrow">Jungle House</p>
                    <h2 className="sidebar-title">AI Wiki</h2>
                    <p className="sidebar-subtitle">Training & Knowledge Hub</p>
                  </div>
                </div>

                <button
                  type="button"
                  className="sidebar-toggle-btn"
                  onClick={handleToggleSidebar}
                  aria-label="Toggle sidebar"
                >
                  <Icon name={isCollapsed ? 'chevronRight' : 'chevronLeft'} />
                </button>
              </div>
            </div>

            <nav className="sidebar-nav">
              {(isStaff || isTeamLead) && (
                <>
                  <div className="sidebar-section-label">Staff Workspace</div>

                  <NavLink className={linkClass} to="/dashboard" onClick={closeMobileAfterClick}>
                    <SidebarIcon name="dashboard" />
                    <span className="sidebar-link-text">Dashboard</span>
                  </NavLink>

                  <NavLink className={linkClass} to="/chat" onClick={closeMobileAfterClick}>
                    <SidebarIcon name="chat" />
                    <span className="sidebar-link-text">AI Chat</span>
                  </NavLink>

                  <NavLink className={linkClass} to="/knowledge" onClick={closeMobileAfterClick}>
                    <SidebarIcon name="knowledge" />
                    <span className="sidebar-link-text">Knowledge Base</span>
                  </NavLink>

                  <NavLink className={linkClass} to="/messages" onClick={closeMobileAfterClick}>
                    <SidebarIcon name="messages" />
                    <span className="sidebar-link-text">Messages</span>
                  </NavLink>

                  <NavLink className={linkClass} to="/notifications" onClick={closeMobileAfterClick}>
                    <SidebarIcon name="notifications" />
                    <span className="sidebar-link-text">Notifications</span>
                  </NavLink>

                  <NavLink className={linkClass} to="/quiz" onClick={closeMobileAfterClick}>
                    <SidebarIcon name="quiz" />
                    <span className="sidebar-link-text">Quiz / Training</span>
                  </NavLink>
                </>
              )}

              {(isTeamLead || isManager) && (
                <>
                  <div className="sidebar-section-label">
                    {isManager ? 'Admin Workspace' : 'Team Lead Workspace'}
                  </div>

                  {isManager && (
                    <NavLink className={linkClass} to="/admin/dashboard" onClick={closeMobileAfterClick}>
                      <SidebarIcon name="dashboard" />
                      <span className="sidebar-link-text">Admin Dashboard</span>
                    </NavLink>
                  )}

                  {isManager && (
                    <NavLink className={linkClass} to="/chat" onClick={closeMobileAfterClick}>
                      <SidebarIcon name="chat" />
                      <span className="sidebar-link-text">AI Chat</span>
                    </NavLink>
                  )}

                  <NavLink className={linkClass} to="/admin/content" onClick={closeMobileAfterClick}>
                    <SidebarIcon name="content" />
                    <span className="sidebar-link-text">Content Management</span>
                  </NavLink>

                  <NavLink
                    className={linkClass}
                    to="/admin/quiz-management"
                    onClick={closeMobileAfterClick}
                  >
                    <SidebarIcon name="quiz" />
                    <span className="sidebar-link-text">Quiz Management</span>
                  </NavLink>

                  {isManager && (
                    <NavLink className={linkClass} to="/messages" onClick={closeMobileAfterClick}>
                      <SidebarIcon name="messages" />
                      <span className="sidebar-link-text">Messages</span>
                    </NavLink>
                  )}

                  {isManager && (
                    <NavLink className={linkClass} to="/admin/review" onClick={closeMobileAfterClick}>
                      <SidebarIcon name="review" />
                      <span className="sidebar-link-text">Review Management</span>
                    </NavLink>
                  )}

                  {isManager && (
                    <NavLink className={linkClass} to="/admin/users" onClick={closeMobileAfterClick}>
                      <SidebarIcon name="users" />
                      <span className="sidebar-link-text">User Management</span>
                    </NavLink>
                  )}

                  {isManager && (
                    <NavLink className={linkClass} to="/admin/ai-settings" onClick={closeMobileAfterClick}>
                      <SidebarIcon name="settings" />
                      <span className="sidebar-link-text">AI Settings</span>
                    </NavLink>
                  )}

                  <NavLink className={linkClass} to="/admin/analytics" onClick={closeMobileAfterClick}>
                    <SidebarIcon name="analytics" />
                    <span className="sidebar-link-text">Analytics</span>
                  </NavLink>

                  <NavLink className={linkClass} to="/admin/security" onClick={closeMobileAfterClick}>
                    <SidebarIcon name="security" />
                    <span className="sidebar-link-text">Security / Monitoring</span>
                  </NavLink>
                </>
              )}

              {(isTeamLead || isManager) && (
                <>
                  <div className="sidebar-section-label">Review</div>

                  <NavLink className={linkClass} to="/escalation" onClick={closeMobileAfterClick}>
                    <SidebarIcon name="escalation" />
                    <span className="sidebar-link-text">Escalation</span>
                  </NavLink>
                </>
              )}

              <div className="sidebar-section-label">Account</div>

              <NavLink className={linkClass} to="/profile" onClick={closeMobileAfterClick}>
                <SidebarIcon name="profile" />
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
                <strong>{user?.name || user?.full_name || 'User'}</strong>
                <span>{user?.role || 'Staff'}</span>
              </span>

              <span className="sidebar-user-arrow">
                <Icon name="chevronRight" />
              </span>
            </button>

            {isUserMenuOpen ? (
              <div className="sidebar-user-menu">
                <div className="sidebar-user-menu-header">
                  <span className="sidebar-user-avatar small-avatar">{getInitial()}</span>

                  <div>
                    <strong>{user?.name || user?.full_name || 'User'}</strong>
                    <span>{user?.role || 'Staff'}</span>
                  </div>
                </div>

                <div className="sidebar-user-menu-divider" />

                <NavLink
                  to="/profile"
                  className="sidebar-user-menu-item"
                  onClick={() => setIsUserMenuOpen(false)}
                >
                  <span className="sidebar-user-menu-icon">
                    <Icon name="profile" />
                  </span>
                  <strong>Profile</strong>
                </NavLink>

                <button
                  type="button"
                  className="sidebar-user-menu-item"
                  onClick={handleLogout}
                >
                  <span className="sidebar-user-menu-icon">
                    <Icon name="logout" />
                  </span>
                  <strong>Log out</strong>
                </button>
              </div>
            ) : null}
          </div>
        </div>
      </aside>
    </>
  );
}
