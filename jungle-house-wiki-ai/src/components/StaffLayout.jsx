import { useCallback, useEffect, useRef, useState } from 'react';
import { NavLink, Outlet, useLocation, useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { StaffChatProvider, useStaffChat } from '../context/StaffChatContext';
import LanguageSelector from '../i18n/LanguageSelector';
import { useLanguage } from '../i18n/LanguageContext';
import { translateServerMessage } from '../i18n/serverMessages';
import { displayStoredText } from '../utils/storedChatText';
import { StaffPreferencesDialog, StaffPreferencesProvider, useStaffPreferences } from './StaffPreferences';

function Symbol({ name, size = 20 }) {
  const paths = {
    menu: <><path d="M4 7h16M4 12h16M4 17h16" /></>,
    panel: <><rect x="3" y="4" width="18" height="16" rx="3"/><path d="M9 4v16" /></>,
    chevronLeft: <><path d="m15 18-6-6 6-6" /></>,
    chevronRight: <><path d="m9 18 6-6-6-6" /></>,
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
    settings: <><path d="M12.22 2h-.44a2 2 0 0 0-2 2v.18a2 2 0 0 1-1 1.73l-.43.25a2 2 0 0 1-2 0l-.15-.08a2 2 0 0 0-2.73.73l-.22.38a2 2 0 0 0 .73 2.73l.15.09a2 2 0 0 1 1 1.74v.5a2 2 0 0 1-1 1.74l-.15.09a2 2 0 0 0-.73 2.73l.22.38a2 2 0 0 0 2.73.73l.15-.08a2 2 0 0 1 2 0l.43.25a2 2 0 0 1 1 1.73V20a2 2 0 0 0 2 2h.44a2 2 0 0 0 2-2v-.18a2 2 0 0 1 1-1.73l.43-.25a2 2 0 0 1 2 0l.15.08a2 2 0 0 0 2.73-.73l.22-.38a2 2 0 0 0-.73-2.73l-.15-.09a2 2 0 0 1-1-1.74v-.5a2 2 0 0 1 1-1.74l.15-.09a2 2 0 0 0 .73-2.73l-.22-.38a2 2 0 0 0-2.73-.73l-.15.08a2 2 0 0 1-2 0l-.43-.25a2 2 0 0 1-1-1.73V4a2 2 0 0 0-2-2Z"/><circle cx="12" cy="12" r="3"/></>,
    tune: <><path d="M4 7h10M18 7h2M4 17h2M10 17h10M14 4v6M8 14v6"/><circle cx="14" cy="7" r="2"/><circle cx="8" cy="17" r="2"/></>,
    sync: <><path d="M20 7v5h-5M4 17v-5h5"/><path d="M5 9a7 7 0 0 1 12-2l3 5M4 12l3 5a7 7 0 0 0 12-2" /></>,
    analytics: <><path d="M4 19V5M4 19h16M8 16v-5M12 16V8M16 16v-3m0-5 4-4m-4 0h4v4" /></>,
    security: <><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10"/><path d="m9.5 12.5 2 2 3.5-4.5" /></>,
    escalation: <><path d="M12 9v4M12 17h.01"/><path d="M10.3 3.9 2.5 17.3A2 2 0 0 0 4.2 20h15.6a2 2 0 0 0 1.7-2.7L13.7 3.9a2 2 0 0 0-3.4 0" /></>,
  };
  return <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{paths[name] || paths.chat}</svg>;
}


function BrandMark({ size = 30, className = '' }) {
  return (
    <span
      className={`jh-brand-mark ${className}`.trim()}
      style={{ '--jh-brand-size': `${size}px` }}
      aria-hidden="true"
    >
      <svg viewBox="0 0 32 32" role="presentation">
        <path
          className="jh-brand-leaf-shape"
          d="M8.2 22.6c.1-7.2 4-11.4 11.6-12.6-.9 7.4-4.8 11.6-11.6 12.6Z"
        />
        <path
          className="jh-brand-leaf-vein"
          d="M8.7 22.7c2.9-5.2 6.2-8.5 10.4-10.7"
        />
        <path
          className="jh-brand-spark"
          d="M23.6 5.2 25 8.7l3.5 1.4-3.5 1.4-1.4 3.5-1.4-3.5-3.5-1.4 3.5-1.4 1.4-3.5Z"
        />
      </svg>
    </span>
  );
}

const staffLinks = [
  { to: '/knowledge', text: 'Knowledge Base', icon: 'book' },
  { to: '/quiz', text: 'Training & Quiz', icon: 'quiz' },
  { to: '/messages', text: 'Messages', icon: 'chat' },
  { to: '/notifications', text: 'Notifications', icon: 'bell' },
];

const managementLinks = [
  { to: '/dashboard', text: 'nav.dashboard', icon: 'dashboard', roles: ['teamlead'] },
  { to: '/admin/dashboard', text: 'nav.managementDashboard', icon: 'dashboard', roles: ['manager', 'admin'] },
  { to: '/admin/content', text: 'nav.contentManagement', icon: 'content', roles: ['teamlead', 'manager', 'admin'] },
  { to: '/admin/quiz-management', text: 'nav.quizManagement', icon: 'quiz', roles: ['teamlead', 'manager', 'admin'] },
  { to: '/admin/review', text: 'nav.reviewManagement', icon: 'review', roles: ['manager', 'admin'] },
  { to: '/admin/users', text: 'nav.userManagement', icon: 'users', roles: ['teamlead', 'manager', 'admin'] },
  { to: '/admin/ai-settings', text: 'nav.aiSettings', icon: 'settings', roles: ['manager', 'admin'] },
  { to: '/admin/notion-sync', text: 'nav.notionSync', icon: 'sync', roles: ['manager', 'admin'] },
  { to: '/admin/analytics', text: 'nav.analytics', icon: 'analytics', roles: ['teamlead', 'manager', 'admin'] },
  { to: '/admin/security', text: 'nav.security', icon: 'security', roles: ['teamlead', 'manager', 'admin'] },
  { to: '/escalation', text: 'nav.escalation', icon: 'escalation', roles: ['teamlead', 'manager', 'admin'] },
];

function StaffShell() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const { sessions, activeSessionId, request } = useStaffChat();
  const { settings, effectiveAppearance, effectiveContrast, t } = useStaffPreferences();
  const { t: appT } = useLanguage();
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
  const fullName = user?.full_name || user?.name || t('role.staff');
  const firstName = fullName.trim().split(/\s+/)[0] || t('role.staff');
  const initial = firstName[0]?.toUpperCase() || 'S';
  const role = String(user?.role || '').trim().toLowerCase().replace(/[\s_-]/g, '');
  const visibleManagementLinks = managementLinks.filter((link) => link.roles.includes(role));
  const isChatRoute = location.pathname === '/chat';
  const workspaceLabel = role === 'manager' || role === 'admin'
    ? t('nav.adminWorkspace')
    : role === 'teamlead'
      ? t('nav.teamLeadWorkspace')
      : t('workspace');
  const roleLabel = role === 'manager' || role === 'admin'
    ? t('role.manager')
    : role === 'teamlead'
      ? t('role.teamlead')
      : t('assistant');

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
    catch (error) { setLogoutError(translateServerMessage(appT, error?.message) || t('staff.logoutFailed')); setProfileOpen(true); }
    finally { logoutBusy.current = false; setLogoutPending(false); }
  };
  const visibleSessions = sessions.filter((item) => item.title?.toLowerCase().includes(search.trim().toLowerCase()));

  return (
    <div
      className={`staff-workspace ${collapsed ? 'staff-is-collapsed' : ''} ${mobileOpen ? 'staff-mobile-open' : ''} ${isChatRoute ? 'staff-chat-route' : ''}`}
      data-jh-theme={effectiveAppearance}
      data-jh-contrast={effectiveContrast}
      data-jh-accent={settings.accent}
      data-jh-text-size={settings.textSize}
      data-jh-density={settings.density}
      data-jh-content-width={settings.contentWidth}
      data-jh-motion={settings.motion}
      lang={settings.language === 'zh' ? 'zh-Hans' : settings.language}
    >
      {mobileOpen && <button type="button" className="staff-overlay" aria-label={t('staff.closeNavigation')} onClick={() => setMobileOpen(false)} />}
      <aside className="staff-sidebar" aria-label={t('layout.staffNav')}>
        <div className="staff-brand">
          <BrandMark size={34} className="staff-brand-icon" />
          {!collapsed && <div><strong>Jungle House AI</strong><small>{roleLabel}</small></div>}
          <button
            type="button"
            className="staff-icon-button staff-collapse-button"
            aria-label={collapsed ? t('staff.expandSidebar') : t('staff.collapseSidebar')}
            title={collapsed ? t('staff.expandSidebar') : t('staff.collapseSidebar')}
            onClick={() => setCollapsed((current) => !current)}
          >
            <Symbol name={collapsed ? 'chevronRight' : 'chevronLeft'} size={20}/>
          </button>
          <button type="button" className="staff-icon-button staff-mobile-close" aria-label={t('staff.closeNavigation')} onClick={() => setMobileOpen(false)}><Symbol name="close"/></button>
        </div>
        <div className="staff-nav-scroll">
          <nav aria-label={t('layout.mainFeatures')} className="staff-primary-links">
            <button type="button" className="staff-nav-link staff-new-chat" onClick={startChat} title={t('newChat')}><Symbol name="edit"/><span>{t('newChat')}</span></button>
            <button type="button" className="staff-nav-link" onClick={() => setSearchOpen(true)} title={t('searchChats')}><Symbol name="search"/><span>{t('searchChats')}</span></button>
            {staffLinks.map((link) => <NavLink key={link.to} className={({isActive}) => `staff-nav-link ${isActive ? 'active' : ''}`} to={link.to} title={t(({ '/knowledge': 'knowledge', '/quiz': 'quiz', '/messages': 'messages', '/notifications': 'notifications' })[link.to])} onClick={() => setMobileOpen(false)}><Symbol name={link.icon}/><span>{t(({ '/knowledge': 'knowledge', '/quiz': 'quiz', '/messages': 'messages', '/notifications': 'notifications' })[link.to])}</span></NavLink>)}
            <button type="button" className="staff-nav-link" aria-expanded={moreOpen} onClick={() => setMoreOpen((current) => !current)} title={t('more')}><Symbol name="more"/><span>{t('more')}</span></button>
            {moreOpen && <div className="staff-more-links"><NavLink to="/profile" onClick={() => setMobileOpen(false)} className="staff-nav-link"><Symbol name="user"/><span>{t('profile')}</span></NavLink><NavLink to="/sop-selection" onClick={() => setMobileOpen(false)} className="staff-nav-link"><Symbol name="book"/><span>{t('sop')}</span></NavLink><button type="button" className="staff-nav-link" onClick={openHistory}><Symbol name="search"/><span>{t('history')}</span></button></div>}
            {visibleManagementLinks.length > 0 && (
              <div className="staff-primary-links staff-management-links" role="group" aria-label={t('layout.managementTools')}>
                <div className="staff-recent-header" aria-hidden="true"><span>{t('nav.management')}</span></div>
                {visibleManagementLinks.map((link) => (
                  <NavLink key={link.to} to={link.to} title={t(link.text)} onClick={() => setMobileOpen(false)} className={({ isActive }) => `staff-nav-link ${isActive ? 'active' : ''}`}>
                    <Symbol name={link.icon}/><span>{t(link.text)}</span>
                  </NavLink>
                ))}
              </div>
            )}
          </nav>
          <div className="staff-recent-header"><span>{t('recent')}</span><button type="button" aria-label={t('staff.openChatHistory')} title={t('staff.openChatHistory')} onClick={openHistory}><Symbol name="search" size={15}/></button></div>
          <div className="staff-recent-list" aria-label={t('layout.recentConversations')}>
            {sessions.length ? sessions.slice(0, 18).map((item) => <div key={item.id} className="staff-recent-row"><button type="button" className={`staff-recent-chat ${String(activeSessionId) === String(item.id) && location.pathname === '/chat' ? 'active' : ''}`} onClick={() => chooseChat(item.id)} title={displayStoredText(item.title, appT)}><Symbol name="chat" size={16}/><span>{displayStoredText(item.title, appT)}</span></button><button type="button" className="staff-delete-recent" onClick={() => deleteChat(item.id)} aria-label={`${t('staff.deleteChat')}: ${displayStoredText(item.title, appT)}`} title={t('staff.deleteChat')}>×</button></div>) : <p className="staff-sidebar-empty">{t('emptyChats')}</p>}
            {sessions.length > 18 && <button type="button" className="staff-show-all" onClick={openHistory}>{t('allChats')} →</button>}
          </div>
        </div>
        <div className="staff-profile-area">
          {profileOpen && <div className="staff-account-menu" role="menu"><div className="staff-account-head"><strong>{fullName}</strong><small>{user?.email || t('role.staff')}</small></div><button type="button" role="menuitem" onClick={() => { setProfileOpen(false); setPreferencesOpen(true); }}><Symbol name="leaf" size={18}/>{t('settings')}</button><NavLink to="/profile" role="menuitem" onClick={() => setProfileOpen(false)}><Symbol name="user" size={18}/> {t('account')}</NavLink><button type="button" role="menuitem" disabled={logoutPending} onClick={signOut}><Symbol name="logout" size={18}/>{logoutPending ? t('loggingOut') : t('logout')}</button>{logoutError && <p role="alert" className="staff-logout-error">{logoutError}</p>}</div>}
          <button type="button" className="staff-profile-trigger" aria-haspopup="menu" aria-expanded={profileOpen} onClick={() => setProfileOpen((current) => !current)}><span className="staff-avatar">{initial}</span><span className="staff-profile-identity"><strong>{fullName}</strong><small>{roleLabel}</small></span><Symbol name="more" size={18}/></button>
        </div>
      </aside>
      <div className="staff-main">
        <header className="staff-topbar"><button type="button" className="staff-icon-button staff-hamburger" onClick={() => setMobileOpen(true)} aria-label={t('staff.openNavigation')}><Symbol name="menu"/></button><div className="staff-topbar-label"><BrandMark size={30}/><span>Jungle House AI</span><small>{workspaceLabel}</small></div><div className="staff-topbar-actions"><LanguageSelector placement="down" /><button type="button" className="staff-icon-button jh-preferences-top-trigger" title={t('settings')} aria-label={t('openSettings')} onClick={() => setPreferencesOpen(true)}><Symbol name="settings" size={19}/></button><NavLink to="/notifications" aria-label={t('nav.notifications')} title={t('nav.notifications')} className="staff-icon-button"><Symbol name="bell" size={20}/></NavLink><NavLink to="/profile" className="staff-avatar staff-avatar-top" aria-label={`${t('profile')}: ${fullName}`} title={fullName}>{initial}</NavLink></div></header>
        <main className={`staff-content ${location.pathname === '/chat' ? 'staff-content-chat' : ''}`} id="staff-content"><Outlet context={{ firstName }}/></main>
      </div>
      {preferencesOpen && <StaffPreferencesDialog onClose={closePreferences} />}
      {searchOpen && <div className="staff-search-backdrop" onMouseDown={(event) => { if (event.target === event.currentTarget) setSearchOpen(false); }}><section className="staff-search-dialog" role="dialog" aria-modal="true" aria-label={t('searchChats')}><div className="staff-search-bar"><Symbol name="search"/><input autoFocus aria-label={t('searchChats')} placeholder={t('searchPlaceholder')} value={search} onChange={(event) => setSearch(event.target.value)}/><button type="button" className="staff-icon-button" aria-label={t('close')} onClick={() => setSearchOpen(false)}><Symbol name="close"/></button></div><div className="staff-search-results">{visibleSessions.length ? visibleSessions.map((item) => <button key={item.id} type="button" onClick={() => chooseChat(item.id)}><Symbol name="chat" size={18}/><span>{displayStoredText(item.title, appT)}</span><small>{item.updated_at}</small></button>) : <p>{t('noMatches')}</p>}</div><button type="button" className="staff-search-history" onClick={openHistory}>{t('viewHistory')} →</button></section></div>}
    </div>
  );
}

export default function StaffLayout() {
  const { user } = useAuth();
  return <StaffPreferencesProvider key={user?.id} user={user}><StaffChatProvider user={user}><StaffShell /></StaffChatProvider></StaffPreferencesProvider>;
}
