import { useCallback, useEffect, useRef, useState } from 'react';
import { NavLink, Outlet, useLocation, useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { StaffChatProvider, useStaffChat } from '../context/StaffChatContext';
import FloatingAIChat from './FloatingAIChat';
import { StaffPreferencesDialog, StaffPreferencesProvider, useStaffPreferences } from './StaffPreferences';

function Symbol({ name, size = 20 }) {
  const paths = {
    menu: <><path d="M4 7h16M4 12h16M4 17h16" /></>,
    panel: <><rect x="3" y="4" width="18" height="16" rx="3"/><path d="M9 4v16" /></>,
    edit: <><path d="M12 5H6a3 3 0 0 0-3 3v10a3 3 0 0 0 3 3h10a3 3 0 0 0 3-3v-6"/><path d="m11 13 9-9a2 2 0 0 1 2 2l-9 9-4 1z" /></>,
    search: <><circle cx="10.8" cy="10.8" r="6.8"/><path d="m16 16 5 5" /></>,
    book: <><path d="M4 5a3 3 0 0 1 3-3h13v18H7a3 3 0 0 0-3 3zM4 5v18M8 7h8M8 11h6" /></>,
    quiz: <><rect x="5" y="3" width="14" height="19" rx="2"/><path d="M9 3h6M9 10l2 2 4-4M9 17h6" /></>,
    chat: <><path d="M4 5h16v12H9l-5 4z"/><path d="M8 10h8M8 13h5" /></>,
    bell: <><path d="M18 9a6 6 0 0 0-12 0c0 6-3 8-3 8h18s-3-2-3-8M10 21h4" /></>,
    more: <><circle cx="5" cy="12" r="1"/><circle cx="12" cy="12" r="1"/><circle cx="19" cy="12" r="1" /></>,
    user: <><circle cx="12" cy="8" r="4"/><path d="M4 21a8 8 0 0 1 16 0" /></>,
    logout: <><path d="M10 17l5-5-5-5M15 12H3M14 3h5a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2h-5" /></>,
    close: <><path d="M5 5l14 14M19 5 5 19" /></>,
    leaf: <><path d="M20 3C9 3 4 8 4 16c0 3 2 5 5 5 8 0 12-7 11-18Z"/><path d="M4 21c2-6 6-10 12-14" /></>,
    dashboard: <><rect x="3" y="3" width="8" height="8" rx="1.5"/><rect x="13" y="3" width="8" height="5" rx="1.5"/><rect x="13" y="10" width="8" height="11" rx="1.5"/><rect x="3" y="13" width="8" height="8" rx="1.5"/></>,
    content: <><path d="M4 6h16M4 12h16M4 18h16M8 6v12" /></>,
    review: <><path d="M12 3 20 7v6c0 5-3.5 7.5-8 8-4.5-.5-8-3-8-8V7z"/><path d="m8.5 12 2.3 2.3 4.7-5" /></>,
    users: <><path d="M16 21v-2a4 4 0 0 0-4-4H7a4 4 0 0 0-4 4v2M9.5 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8M22 21v-2a4 4 0 0 0-3-3.9M16 3.3a4 4 0 0 1 0 7.4" /></>,
    settings: <><circle cx="12" cy="12" r="3"/><path d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41m11.32 11.32 1.41 1.41M2 12h2m16 0h2M4.93 19.07l1.41-1.41M17.66 6.34l1.41-1.41" /></>,
    sync: <><path d="M20 7v5h-5M4 17v-5h5"/><path d="M5 9a7 7 0 0 1 12-2l3 5M4 12l3 5a7 7 0 0 0 12-2" /></>,
    analytics: <><path d="M4 19V5M4 19h16M8 16v-5M12 16V8M16 16v-3m0-5 4-4m-4 0h4v4" /></>,
    security: <><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10"/><path d="m9.5 12.5 2 2 3.5-4.5" /></>,
    escalation: <><path d="M12 9v4M12 17h.01"/><path d="M10.3 3.9 2.5 17.3A2 2 0 0 0 4.2 20h15.6a2 2 0 0 0 1.7-2.7L13.7 3.9a2 2 0 0 0-3.4 0" /></>,
  };
  return <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{paths[name] || paths.chat}</svg>;
}

const staffLinks = [
  { to: '/knowledge', text: 'Knowledge Base', icon: 'book' },
  { to: '/quiz', text: 'Training & Quiz', icon: 'quiz' },
  { to: '/messages', text: 'Messages', icon: 'chat' },
  { to: '/notifications', text: 'Notifications', icon: 'bell' },
];

// Keep navigation roles in sync with App.jsx; backend and RoleRoute remain
// responsible for actual authorisation, not whether a sidebar link is visible.
const managementLinks = [
  { to: '/dashboard', text: 'Dashboard', icon: 'dashboard', roles: ['teamlead'] },
  { to: '/admin/dashboard', text: 'Management Dashboard', icon: 'dashboard', roles: ['manager', 'admin'] },
  { to: '/admin/content', text: 'Content Management', icon: 'content', roles: ['teamlead', 'manager', 'admin'] },
  { to: '/admin/quiz-management', text: 'Quiz Management', icon: 'quiz', roles: ['teamlead', 'manager', 'admin'] },
  { to: '/admin/review', text: 'Review Management', icon: 'review', roles: ['teamlead', 'manager', 'admin'] },
  { to: '/admin/users', text: 'User Management', icon: 'users', roles: ['teamlead', 'manager', 'admin'] },
  { to: '/admin/ai-settings', text: 'AI Settings', icon: 'settings', roles: ['manager', 'admin'] },
  { to: '/admin/notion-sync', text: 'Notion Sync', icon: 'sync', roles: ['manager', 'admin'] },
  { to: '/admin/analytics', text: 'Analytics', icon: 'analytics', roles: ['teamlead', 'manager', 'admin'] },
  { to: '/admin/security', text: 'Security Monitoring', icon: 'security', roles: ['teamlead', 'manager', 'admin'] },
  { to: '/escalation', text: 'Escalation', icon: 'escalation', roles: ['teamlead', 'manager', 'admin'] },
];

function StaffShell() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const { sessions, activeSessionId, request } = useStaffChat();
  const { settings, effectiveAppearance, effectiveContrast, t } = useStaffPreferences();
  const [mobileOpen, setMobileOpen] = useState(false);
  const [collapsed, setCollapsed] = useState(false);
  const [searchOpen, setSearchOpen] = useState(false);
  const [search, setSearch] = useState('');
  const [moreOpen, setMoreOpen] = useState(false);
  const [profileOpen, setProfileOpen] = useState(false);
  const [preferencesOpen, setPreferencesOpen] = useState(false);
  const closePreferences = useCallback(() => setPreferencesOpen(false), []);
  const [logoutPending, setLogoutPending] = useState(false);
  const [logoutError, setLogoutError] = useState('');
  const logoutBusy = useRef(false);
  const fullName = user?.full_name || user?.name || 'Staff';
  const firstName = fullName.trim().split(/\s+/)[0] || 'Staff';
  const initial = firstName[0]?.toUpperCase() || 'S';
  const role = String(user?.role || '').trim().toLowerCase().replace(/[\s_-]/g, '');
  const visibleManagementLinks = managementLinks.filter((link) => link.roles.includes(role));

  useEffect(() => { setMobileOpen(false); setMoreOpen(false); setSearchOpen(false); setProfileOpen(false); setPreferencesOpen(false); }, [location.pathname]);
  useEffect(() => {
    const handleEscape = (event) => {
      if (event.key === 'Escape') { setMobileOpen(false); setMoreOpen(false); setSearchOpen(false); setProfileOpen(false); setPreferencesOpen(false); }
    };
    window.addEventListener('keydown', handleEscape);
    return () => window.removeEventListener('keydown', handleEscape);
  }, []);

  const startChat = () => { request('new'); navigate('/chat'); setMobileOpen(false); };
  const chooseChat = (id) => { request('select', id); navigate('/chat'); setMobileOpen(false); setSearchOpen(false); };
  const deleteChat = (id) => { request('delete', id); navigate('/chat'); setMobileOpen(false); };
  const openHistory = () => { request('history'); navigate('/chat'); setMobileOpen(false); setSearchOpen(false); };
  const signOut = async () => {
    if (logoutBusy.current) return;
    logoutBusy.current = true; setLogoutPending(true); setLogoutError('');
    try { await logout(); navigate('/login', { replace: true }); }
    catch (error) { setLogoutError(error?.message || 'Could not log out. Please retry.'); setProfileOpen(true); }
    finally { logoutBusy.current = false; setLogoutPending(false); }
  };
  const visibleSessions = sessions.filter((item) => item.title?.toLowerCase().includes(search.trim().toLowerCase()));

  return (
    <div className={`staff-workspace ${collapsed ? 'staff-is-collapsed' : ''} ${mobileOpen ? 'staff-mobile-open' : ''}`} data-jh-theme={effectiveAppearance} data-jh-contrast={effectiveContrast} data-jh-accent={settings.accent} lang={settings.language === 'zh' ? 'zh-Hans' : settings.language}>
      {mobileOpen && <button type="button" className="staff-overlay" aria-label="Close navigation" onClick={() => setMobileOpen(false)} />}
      <aside className="staff-sidebar" aria-label="Staff navigation">
        <div className="staff-brand">
          <span className="staff-brand-icon"><Symbol name="leaf" size={25}/></span>
          {!collapsed && <div><strong>Jungle House AI</strong><small>{t('assistant')}</small></div>}
          <button type="button" className="staff-icon-button staff-collapse-button" aria-label={collapsed ? 'Expand sidebar' : 'Collapse sidebar'} onClick={() => setCollapsed((current) => !current)}><Symbol name="panel" size={19}/></button>
          <button type="button" className="staff-icon-button staff-mobile-close" aria-label="Close navigation" onClick={() => setMobileOpen(false)}><Symbol name="close"/></button>
        </div>
        <div className="staff-nav-scroll">
          <nav aria-label="Main features" className="staff-primary-links">
            <button type="button" className="staff-nav-link staff-new-chat" onClick={startChat} title="New chat"><Symbol name="edit"/><span>{t('newChat')}</span></button>
            <button type="button" className="staff-nav-link" onClick={() => setSearchOpen(true)} title="Search chats"><Symbol name="search"/><span>{t('searchChats')}</span></button>
            {staffLinks.map((link) => <NavLink key={link.to} className={({isActive}) => `staff-nav-link ${isActive ? 'active' : ''}`} to={link.to} title={link.text} onClick={() => setMobileOpen(false)}><Symbol name={link.icon}/><span>{t(({ '/knowledge': 'knowledge', '/quiz': 'quiz', '/messages': 'messages', '/notifications': 'notifications' })[link.to])}</span></NavLink>)}
            <button type="button" className="staff-nav-link" aria-expanded={moreOpen} onClick={() => setMoreOpen((current) => !current)} title="More"><Symbol name="more"/><span>{t('more')}</span></button>
            {moreOpen && <div className="staff-more-links"><NavLink to="/profile" onClick={() => setMobileOpen(false)} className="staff-nav-link"><Symbol name="user"/><span>{t('profile')}</span></NavLink><NavLink to="/sop-selection" onClick={() => setMobileOpen(false)} className="staff-nav-link"><Symbol name="book"/><span>{t('sop')}</span></NavLink><button type="button" className="staff-nav-link" onClick={openHistory}><Symbol name="search"/><span>{t('history')}</span></button></div>}
            {visibleManagementLinks.length > 0 && (
              <div className="staff-primary-links staff-management-links" role="group" aria-label="Management tools">
                <div className="staff-recent-header" aria-hidden="true"><span>Management</span></div>
                {visibleManagementLinks.map((link) => (
                  <NavLink
                    key={link.to}
                    to={link.to}
                    title={link.text}
                    onClick={() => setMobileOpen(false)}
                    className={({ isActive }) => `staff-nav-link ${isActive ? 'active' : ''}`}
                  >
                    <Symbol name={link.icon}/><span>{link.text}</span>
                  </NavLink>
                ))}
              </div>
            )}
          </nav>
          <div className="staff-recent-header"><span>{t('recent')}</span><button type="button" aria-label="Open chat history" title="Open chat history" onClick={openHistory}><Symbol name="search" size={15}/></button></div>
          <div className="staff-recent-list" aria-label="Recent conversations">
            {sessions.length ? sessions.slice(0, 18).map((item) => <div key={item.id} className="staff-recent-row"><button type="button" className={`staff-recent-chat ${String(activeSessionId) === String(item.id) && location.pathname === '/chat' ? 'active' : ''}`} onClick={() => chooseChat(item.id)} title={item.title}><Symbol name="chat" size={16}/><span>{item.title}</span></button><button type="button" className="staff-delete-recent" onClick={() => deleteChat(item.id)} aria-label={`Delete ${item.title}`} title="Delete chat">×</button></div>) : <p className="staff-sidebar-empty">{t('emptyChats')}</p>}
            {sessions.length > 18 && <button type="button" className="staff-show-all" onClick={openHistory}>{t('allChats')} →</button>}
          </div>
        </div>
        <div className="staff-profile-area">
          {profileOpen && <div className="staff-account-menu" role="menu"><div className="staff-account-head"><strong>{fullName}</strong><small>{user?.email || 'Staff'}</small></div><button type="button" role="menuitem" onClick={() => { setProfileOpen(false); setPreferencesOpen(true); }}><Symbol name="leaf" size={18}/>{t('settings')}</button><NavLink to="/profile" role="menuitem" onClick={() => setProfileOpen(false)}><Symbol name="user" size={18}/> {t('account')}</NavLink><button type="button" role="menuitem" disabled={logoutPending} onClick={signOut}><Symbol name="logout" size={18}/>{logoutPending ? t('loggingOut') : t('logout')}</button>{logoutError && <p role="alert" className="staff-logout-error">{logoutError}</p>}</div>}
          <button type="button" className="staff-profile-trigger" aria-haspopup="menu" aria-expanded={profileOpen} onClick={() => setProfileOpen((current) => !current)}><span className="staff-avatar">{initial}</span><span className="staff-profile-identity"><strong>{fullName}</strong><small>{t('assistant')}</small></span><Symbol name="more" size={18}/></button>
        </div>
      </aside>
      <div className="staff-main">
        <header className="staff-topbar"><button type="button" className="staff-icon-button staff-hamburger" onClick={() => setMobileOpen(true)} aria-label="Open navigation"><Symbol name="menu"/></button><div className="staff-topbar-label"><Symbol name="leaf" size={19}/><span>Jungle House AI</span><small>{t('workspace')}</small></div><div className="staff-topbar-actions"><button type="button" className="staff-icon-button jh-preferences-top-trigger" title={t('settings')} aria-label={t('openSettings')} onClick={() => setPreferencesOpen(true)}><Symbol name="more" size={20}/></button><NavLink to="/notifications" aria-label="Notifications" title="Notifications" className="staff-icon-button"><Symbol name="bell" size={20}/></NavLink><NavLink to="/profile" className="staff-avatar staff-avatar-top" aria-label={`My profile: ${fullName}`} title={fullName}>{initial}</NavLink></div></header>
        <main className={`staff-content ${location.pathname === '/chat' ? 'staff-content-chat' : ''}`} id="staff-content"><Outlet context={{ firstName }}/></main>
      </div>
      {location.pathname !== '/chat' && <FloatingAIChat />}
      {preferencesOpen && <StaffPreferencesDialog onClose={closePreferences} />}
      {searchOpen && <div className="staff-search-backdrop" onMouseDown={(event) => { if (event.target === event.currentTarget) setSearchOpen(false); }}><section className="staff-search-dialog" role="dialog" aria-modal="true" aria-label="Search conversations"><div className="staff-search-bar"><Symbol name="search"/><input autoFocus aria-label="Search chats" placeholder={t('searchPlaceholder')} value={search} onChange={(event) => setSearch(event.target.value)}/><button type="button" className="staff-icon-button" aria-label="Close search" onClick={() => setSearchOpen(false)}><Symbol name="close"/></button></div><div className="staff-search-results">{visibleSessions.length ? visibleSessions.map((item) => <button key={item.id} type="button" onClick={() => chooseChat(item.id)}><Symbol name="chat" size={18}/><span>{item.title}</span><small>{item.updated_at}</small></button>) : <p>{t('noMatches')}</p>}</div><button type="button" className="staff-search-history" onClick={openHistory}>{t('viewHistory')} →</button></section></div>}
    </div>
  );
}

export default function StaffLayout() {
  const { user } = useAuth();
  return <StaffPreferencesProvider key={user?.id} user={user}><StaffChatProvider user={user}><StaffShell /></StaffChatProvider></StaffPreferencesProvider>;
}
