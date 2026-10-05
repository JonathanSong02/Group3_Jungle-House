import { useEffect, useRef, useState } from 'react';
import PageHeader from '../../components/PageHeader';
import api from '../../services/api';
import { useAuth } from '../../context/AuthContext';
import './styles/NotionSync.css';

// Notion's redirect_uri has to be the backend's own real, stable public
// URL (what's registered in the Notion integration settings) -- NOT the
// "/api" same-origin Vercel proxy path everything else in this app uses --
// so the OAuth popup ends up on the Railway domain directly, same as the
// other places in this app that need the raw backend origin (see
// ArticleDetail.jsx/Chat.jsx's VITE_STATIC_BASE_URL/VITE_BACKEND_PUBLIC_URL
// fallback chain, reused here for the postMessage origin check below).
const NOTION_OAUTH_BACKEND_URL = String(
  import.meta.env.VITE_STATIC_BASE_URL ||
  import.meta.env.VITE_BACKEND_PUBLIC_URL ||
  (typeof window !== 'undefined' &&
    ['localhost', '127.0.0.1'].includes(window.location.hostname)
    ? 'http://127.0.0.1:5000'
    : 'https://group3jungle-house-production.up.railway.app')
).replace(/\/+$/, '');

const NOTION_OAUTH_ORIGIN = new URL(NOTION_OAUTH_BACKEND_URL).origin;

export default function NotionSync() {
  const { user } = useAuth();
  const actorId = user?.id || user?.user_id || null;

  const [config, setConfig] = useState(null);
  const [loading, setLoading] = useState(true);
  const [connecting, setConnecting] = useState(false);
  const [disconnecting, setDisconnecting] = useState(false);
  const [checking, setChecking] = useState(false);

  const [message, setMessage] = useState(() => {
    const params = new URLSearchParams(window.location.search);
    const connected = params.get('connected');
    const error = params.get('error');

    if (connected) return 'Notion connected successfully.';
    if (error) return `Notion connection failed: ${error.replace(/_/g, ' ')}`;
    return '';
  });

  const [checkResult, setCheckResult] = useState(null);
  const [jobs, setJobs] = useState([]);
  const [pending, setPending] = useState([]);
  const [expandedPendingId, setExpandedPendingId] = useState(null);
  const [resolvingId, setResolvingId] = useState(null);

  // Trash: a temporary hold for pending Notion items -- content/images kept
  // until Restore or Delete Permanently, see the Trash tab below.
  const [activeTab, setActiveTab] = useState('pending');
  const [trashed, setTrashed] = useState([]);
  const [selectedIds, setSelectedIds] = useState([]);
  const [bulkProcessing, setBulkProcessing] = useState(false);
  const [singleActionId, setSingleActionId] = useState(null);

  const [storageAudit, setStorageAudit] = useState(null);
  const [runningAudit, setRunningAudit] = useState(false);
  const [cleaningStorage, setCleaningStorage] = useState(false);

  // Obsolete: Notion pages permanently deleted from stored content, kept as
  // a lightweight record so a future sync recognises them instead of
  // re-staging them as brand-new Pending items. Deliberately not folded
  // into `activeList`/the bulk toolbar below -- its cards show different
  // fields (deleted/modified dates, Updated-in-Notion badge) and only ever
  // have one action (Restore), so it gets its own small render branch.
  const [obsolete, setObsolete] = useState([]);
  const [expandedObsoleteId, setExpandedObsoleteId] = useState(null);
  const [restoringObsoleteId, setRestoringObsoleteId] = useState(null);

  const oauthPopupRef = useRef(null);
  const oauthPopupPollRef = useRef(null);

  // Lets a manager point this deployment at a different Notion public
  // integration (its own Client ID/Secret) -- e.g. a new client wants their
  // own app on the Notion consent screen -- without needing Railway access.
  const [appConfig, setAppConfig] = useState(null);
  const [appForm, setAppForm] = useState({ clientId: '', clientSecret: '' });
  const [savingAppConfig, setSavingAppConfig] = useState(false);
  const [resettingAppConfig, setResettingAppConfig] = useState(false);
  const [appConfigMessage, setAppConfigMessage] = useState('');

  const fetchConfig = async () => {
    try {
      setLoading(true);
      const response = await api.get('/notion-sync/config');
      setConfig(response.data?.config || null);
    } catch (error) {
      console.error('Fetch Notion sync config error:', error);
      setMessage('Failed to load Notion connection status.');
    } finally {
      setLoading(false);
    }
  };

  const fetchAppConfig = async () => {
    try {
      const response = await api.get('/notion-sync/oauth/app-config');
      const nextAppConfig = response.data?.appConfig || null;
      setAppConfig(nextAppConfig);
      setAppForm((prev) => ({ ...prev, clientId: nextAppConfig?.clientId || '' }));
    } catch (error) {
      console.error('Fetch Notion app config error:', error);
    }
  };

  const handleAppFormChange = (event) => {
    const { name, value } = event.target;
    setAppForm((prev) => ({ ...prev, [name]: value }));
  };

  const handleSaveAppConfig = async (event) => {
    event.preventDefault();

    if (!appForm.clientId.trim() || !appForm.clientSecret.trim()) {
      setAppConfigMessage('Both Client ID and Client Secret are required.');
      return;
    }

    try {
      setSavingAppConfig(true);
      setAppConfigMessage('');

      const response = await api.post('/notion-sync/oauth/app-config', {
        user_id: actorId,
        clientId: appForm.clientId.trim(),
        clientSecret: appForm.clientSecret.trim(),
      });

      setAppConfigMessage(response.data?.message || 'Notion app credentials saved.');
      setAppConfig(response.data?.appConfig || null);
      // Never keep the raw secret sitting in state longer than needed.
      setAppForm((prev) => ({ ...prev, clientSecret: '' }));
    } catch (error) {
      console.error('Save Notion app config error:', error);
      setAppConfigMessage(
        error.response?.data?.message || 'Failed to save Notion app credentials.'
      );
    } finally {
      setSavingAppConfig(false);
    }
  };

  const handleResetAppConfig = async () => {
    try {
      setResettingAppConfig(true);
      setAppConfigMessage('');

      const response = await api.delete('/notion-sync/oauth/app-config', {
        data: { user_id: actorId },
      });

      setAppConfigMessage(response.data?.message || "Reverted to the server's default Notion app.");
      setAppConfig(response.data?.appConfig || null);
      setAppForm({ clientId: response.data?.appConfig?.clientId || '', clientSecret: '' });
    } catch (error) {
      console.error('Reset Notion app config error:', error);
      setAppConfigMessage(
        error.response?.data?.message || 'Failed to reset Notion app credentials.'
      );
    } finally {
      setResettingAppConfig(false);
    }
  };

  const fetchJobs = async () => {
    try {
      const response = await api.get('/notion-sync/jobs');
      setJobs(Array.isArray(response.data?.jobs) ? response.data.jobs : []);
    } catch (error) {
      console.error('Fetch Notion sync jobs error:', error);
    }
  };

  const fetchPending = async () => {
    try {
      const response = await api.get('/notion-sync/pending-updates', { params: { status: 'pending' } });
      setPending(Array.isArray(response.data?.pending) ? response.data.pending : []);
    } catch (error) {
      console.error('Fetch Notion pending updates error:', error);
    }
  };

  const fetchTrashed = async () => {
    try {
      const response = await api.get('/notion-sync/pending-updates', { params: { status: 'trashed' } });
      setTrashed(Array.isArray(response.data?.pending) ? response.data.pending : []);
    } catch (error) {
      console.error('Fetch Notion trashed updates error:', error);
    }
  };

  const fetchObsolete = async () => {
    try {
      const response = await api.get('/notion-sync/obsolete');
      setObsolete(Array.isArray(response.data?.obsolete) ? response.data.obsolete : []);
    } catch (error) {
      console.error('Fetch Notion obsolete articles error:', error);
    }
  };

  const handleCheckForUpdates = async ({ silent } = {}) => {
    try {
      setChecking(true);
      if (!silent) setMessage('');
      setCheckResult(null);

      const response = await api.post('/notion-sync/check', {
        user_id: actorId,
      });

      setCheckResult(response.data);
      if (!silent) setMessage(response.data?.message || '');
      await Promise.all([fetchJobs(), fetchPending(), fetchObsolete()]);
    } catch (error) {
      console.error('Check Notion for updates error:', error);
      if (!silent) {
        setMessage(
          error.response?.data?.message || 'Failed to check Notion for updates.'
        );
      }
      if (error.response?.data?.connectionStatus === 'reconnect_required') {
        // The connection just flipped to needing reconnect -- refresh so
        // the status card/button reflect that instead of only showing the
        // error text while still looking "connected".
        fetchConfig();
      }
    } finally {
      setChecking(false);
    }
  };

  const stopWatchingOauthPopup = () => {
    if (oauthPopupPollRef.current) {
      clearInterval(oauthPopupPollRef.current);
      oauthPopupPollRef.current = null;
    }
    oauthPopupRef.current = null;
  };

  const finishConnectAttempt = (statusMessage, { connected } = {}) => {
    stopWatchingOauthPopup();
    setConnecting(false);
    if (statusMessage) setMessage(statusMessage);

    fetchConfig();
    if (connected) {
      handleCheckForUpdates({ silent: true });
    } else {
      fetchJobs();
      fetchPending();
    }
  };

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const connected = params.get('connected');
    const error = params.get('error');

    if (connected || error) {
      window.history.replaceState({}, '', window.location.pathname);
    }

    fetchConfig();
    fetchJobs();
    fetchPending();
    fetchTrashed();
    fetchObsolete();
    fetchAppConfig();

    if (connected) {
      setMessage('Notion connected successfully.');
      handleCheckForUpdates({ silent: true });
    } else if (error) {
      setMessage(`Notion connection failed: ${error.replace(/_/g, ' ')}`);
    }

    // Primary path: the OAuth callback runs in a popup window (opened by
    // handleConnect below) and posts the result back here via
    // window.postMessage instead of navigating this tab away, so the admin
    // never loses their place on this page. The ?connected=1/?error=...
    // query params handled above are only the fallback for when the popup
    // was blocked and the callback had to redirect this tab directly.
    const handleOauthMessage = (event) => {
      if (event.origin !== NOTION_OAUTH_ORIGIN) return;
      if (!event.data || event.data.source !== 'jungle-house-notion-oauth') return;

      if (event.data.status === 'connected') {
        finishConnectAttempt('Notion connected successfully.', { connected: true });
      } else {
        const detail = event.data.detail || 'connection_failed';
        finishConnectAttempt(`Notion connection failed: ${detail.replace(/_/g, ' ')}`);
      }
    };

    window.addEventListener('message', handleOauthMessage);
    return () => {
      window.removeEventListener('message', handleOauthMessage);
      stopWatchingOauthPopup();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleConnect = async () => {
    setConnecting(true);
    setMessage('');

    // Open the popup synchronously (before the await below) so browsers
    // don't treat it as an unrequested popup and block it.
    const popup = window.open(
      '',
      'jungle-house-notion-oauth',
      'width=600,height=720,menubar=no,toolbar=no,status=no'
    );

    try {
      const response = await api.post('/notion-sync/oauth/start', {
        user_id: actorId,
      });

      const authorizeUrl = response.data?.authorizeUrl;

      if (!authorizeUrl) {
        throw new Error('No authorization URL returned.');
      }

      if (popup && !popup.closed) {
        oauthPopupRef.current = popup;
        popup.location.href = authorizeUrl;

        // If the admin closes the popup themselves without finishing
        // login, don't leave the button stuck on "Opening Notion...".
        oauthPopupPollRef.current = setInterval(() => {
          if (oauthPopupRef.current && oauthPopupRef.current.closed) {
            finishConnectAttempt(null);
          }
        }, 500);
      } else {
        // Popup blocked -- fall back to redirecting this tab, same as the
        // callback's own fallback when it finds no opener.
        window.location.href = authorizeUrl;
      }
    } catch (error) {
      if (popup && !popup.closed) popup.close();
      console.error('Start Notion OAuth error:', error);
      setMessage(
        error.response?.data?.message || 'Failed to start connecting to Notion.'
      );
      setConnecting(false);
    }
  };

  const handleDisconnect = async () => {
    if (
      !window.confirm(
        'Disconnect this Notion workspace?\n\nFuture Notion syncs will stop until the workspace is reconnected. Existing Knowledge Base articles will not be deleted.'
      )
    ) {
      return;
    }

    try {
      setDisconnecting(true);
      setMessage('');

      const response = await api.post('/notion-sync/disconnect', {
        user_id: actorId,
      });

      setMessage(response.data?.message || 'Notion disconnected.');
      setConfig(null);
      setCheckResult(null);
      setPending([]);
    } catch (error) {
      console.error('Disconnect Notion error:', error);
      setMessage(
        error.response?.data?.message || 'Failed to disconnect Notion.'
      );
    } finally {
      setDisconnecting(false);
    }
  };

  const handleResolvePending = async (pendingId, action) => {
    try {
      setResolvingId(pendingId);
      setMessage('');

      const response = await api.post(
        `/notion-sync/pending-updates/${pendingId}/${action}`,
        { user_id: actorId }
      );

      setMessage(response.data?.message || 'Done.');
      setPending((prev) => prev.filter((item) => item.id !== pendingId));

      if (expandedPendingId === pendingId) {
        setExpandedPendingId(null);
      }

      await fetchJobs();
    } catch (error) {
      console.error(`Resolve Notion pending update (${action}) error:`, error);
      setMessage(
        error.response?.data?.message ||
          'Failed to resolve this update. It may have already been handled.'
      );
      fetchPending();
    } finally {
      setResolvingId(null);
    }
  };

  const handleTrashItem = async (pendingId) => {
    try {
      setSingleActionId(pendingId);
      setMessage('');

      const response = await api.post(`/notion-sync/pending-updates/${pendingId}/trash`, {
        user_id: actorId,
      });

      setMessage(response.data?.message || 'Moved to Trash.');
      setPending((prev) => prev.filter((item) => item.id !== pendingId));
      setSelectedIds((prev) => prev.filter((id) => id !== pendingId));
      fetchTrashed();
    } catch (error) {
      console.error('Trash Notion pending update error:', error);
      setMessage(error.response?.data?.message || 'Failed to move this update to Trash.');
    } finally {
      setSingleActionId(null);
    }
  };

  const handleRestoreItem = async (pendingId) => {
    try {
      setSingleActionId(pendingId);
      setMessage('');

      const response = await api.post(`/notion-sync/pending-updates/${pendingId}/restore`, {
        user_id: actorId,
      });

      setMessage(response.data?.message || 'Restored to Pending.');
      setTrashed((prev) => prev.filter((item) => item.id !== pendingId));
      setSelectedIds((prev) => prev.filter((id) => id !== pendingId));
      fetchPending();
    } catch (error) {
      console.error('Restore Notion pending update error:', error);
      setMessage(error.response?.data?.message || 'Failed to restore this update.');
    } finally {
      setSingleActionId(null);
    }
  };

  const handlePermanentDeleteItem = async (pendingId) => {
    const item = trashed.find((t) => t.id === pendingId);
    const isNewPage = !item || item.article_id === null || item.article_id === undefined;

    const confirmText = isNewPage
      ? 'Move this article to Obsolete and permanently delete its stored files?\n\n' +
        'The stored article content and downloaded images will be permanently removed.\n\n' +
        'A lightweight Obsolete record will remain so the system can recognise this Notion page during future syncs. ' +
        'If the Notion page is updated later, the Obsolete section will show that a newer version is available.'
      : 'Permanently delete this item and its unused local images/files? ' +
        'This only discards the proposed edit -- the live Knowledge Base article is not affected. This cannot be undone.';

    if (!window.confirm(confirmText)) {
      return;
    }

    try {
      setSingleActionId(pendingId);
      setMessage('');

      const response = await api.delete(`/notion-sync/pending-updates/${pendingId}`, {
        data: { user_id: actorId },
      });

      const deletedFiles = response.data?.deletedFiles ?? 0;
      setMessage(
        `${response.data?.message || 'Permanently deleted.'} ${deletedFiles} unused file(s) removed from storage.`
      );
      setTrashed((prev) => prev.filter((item) => item.id !== pendingId));
      setSelectedIds((prev) => prev.filter((id) => id !== pendingId));
      if (response.data?.obsoleteCreated) {
        fetchObsolete();
      }
    } catch (error) {
      console.error('Permanent delete Notion pending update error:', error);
      setMessage(error.response?.data?.message || 'Failed to permanently delete this update.');
    } finally {
      setSingleActionId(null);
    }
  };

  const handleRestoreObsolete = async (obsoleteId) => {
    try {
      setRestoringObsoleteId(obsoleteId);
      setMessage('');

      const response = await api.post(`/notion-sync/obsolete/${obsoleteId}/restore`, {
        user_id: actorId,
      });

      setMessage(response.data?.message || 'Fetched the latest Notion version. Review it in Pending.');
      setObsolete((prev) => prev.filter((item) => item.id !== obsoleteId));
      if (expandedObsoleteId === obsoleteId) setExpandedObsoleteId(null);
      await fetchPending();
    } catch (error) {
      console.error('Restore Notion obsolete article error:', error);
      setMessage(error.response?.data?.message || 'Failed to restore this article.');
      if (error.response?.data?.connectionStatus === 'reconnect_required') {
        fetchConfig();
      }
      // A 409 (source page inaccessible) marks the record 'missing'
      // server-side -- refresh so the card reflects that instead of
      // silently staying stale until the next full page load.
      fetchObsolete();
    } finally {
      setRestoringObsoleteId(null);
    }
  };

  const activeList = activeTab === 'pending' ? pending : trashed;

  const toggleSelection = (id) => {
    setSelectedIds((prev) => (prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]));
  };

  const toggleSelectAllVisible = () => {
    const visibleIds = activeList.map((item) => item.id);
    const allSelected = visibleIds.length > 0 && visibleIds.every((id) => selectedIds.includes(id));
    setSelectedIds(allSelected ? [] : visibleIds);
  };

  const switchTab = (tab) => {
    setActiveTab(tab);
    setSelectedIds([]);
    setMessage('');
  };

  // Shared by the two simple bulk actions (trash/restore) -- same
  // validation, same confirm-before-acting safety net, same success/error
  // handling shape, mirroring runBulkAction in ContentManagement.jsx.
  const runBulkAction = async ({ endpoint, confirmText, successFallback, errorFallback }) => {
    const idsToUse = selectedIds.filter((id) => activeList.some((item) => item.id === id));
    if (idsToUse.length === 0) return;

    if (confirmText && !window.confirm(confirmText(idsToUse.length))) return;

    try {
      setBulkProcessing(true);
      setMessage('');

      const response = await api.post(endpoint, { ids: idsToUse, user_id: actorId });

      setMessage(response.data?.message || successFallback(idsToUse.length));
      setSelectedIds([]);
      await Promise.all([fetchPending(), fetchTrashed()]);
    } catch (error) {
      console.error(`Bulk action error (${endpoint}):`, error);
      setMessage(error.response?.data?.message || errorFallback);
    } finally {
      setBulkProcessing(false);
    }
  };

  const bulkTrashSelected = () =>
    runBulkAction({
      endpoint: '/notion-sync/pending-updates/bulk-trash',
      confirmText: (count) => `Move ${count} selected item(s) to Trash?`,
      successFallback: (count) => `${count} item(s) moved to Trash.`,
      errorFallback: 'Unable to move selected items to Trash.',
    });

  const bulkRestoreSelected = () =>
    runBulkAction({
      endpoint: '/notion-sync/pending-updates/bulk-restore',
      confirmText: null,
      successFallback: (count) => `${count} item(s) restored.`,
      errorFallback: 'Unable to restore selected items.',
    });

  const bulkPermanentDeleteSelected = async () => {
    const idsToUse = selectedIds.filter((id) => activeList.some((item) => item.id === id));
    if (idsToUse.length === 0) return;

    if (
      !window.confirm(
        `Move ${idsToUse.length} selected item(s) to Obsolete and permanently delete their stored files?\n\n` +
        'Stored content and downloaded images will be removed. A lightweight Obsolete record is kept for each ' +
        'new page so future syncs recognise it instead of showing it again. This cannot be undone.'
      )
    ) {
      return;
    }

    try {
      setBulkProcessing(true);
      setMessage('');

      const response = await api.post('/notion-sync/pending-updates/bulk-delete', {
        ids: idsToUse,
        user_id: actorId,
      });

      const deletedArticles = response.data?.deletedArticles ?? 0;
      const deletedFiles = response.data?.deletedFiles ?? 0;
      const obsoleteCreated = response.data?.obsoleteCreated ?? 0;
      setMessage(`${deletedArticles} item(s) permanently deleted. ${deletedFiles} unused file(s) removed from storage.`);
      setSelectedIds([]);
      await Promise.all([fetchPending(), fetchTrashed()]);
      if (obsoleteCreated) {
        fetchObsolete();
      }
    } catch (error) {
      console.error('Bulk permanent delete error:', error);
      setMessage(error.response?.data?.message || 'Unable to permanently delete selected items.');
    } finally {
      setBulkProcessing(false);
    }
  };

  const formatBytes = (bytes) => {
    if (!bytes) return '0 MB';
    const mb = bytes / (1024 * 1024);
    return mb < 1 ? `${Math.max(1, Math.round(bytes / 1024))} KB` : `${mb.toFixed(1)} MB`;
  };

  const handleRunStorageAudit = async () => {
    try {
      setRunningAudit(true);
      setMessage('');

      const response = await api.get('/notion-sync/storage-audit');
      setStorageAudit(response.data?.audit || null);
    } catch (error) {
      console.error('Notion storage audit error:', error);
      setMessage(error.response?.data?.message || 'Failed to run the storage audit.');
    } finally {
      setRunningAudit(false);
    }
  };

  const handleCleanStorage = async () => {
    const orphanCount = storageAudit?.orphanFileCount || 0;
    if (orphanCount === 0) return;

    if (
      !window.confirm(
        `Permanently remove ${orphanCount} unused file(s) from storage (about ${formatBytes(
          storageAudit?.estimatedReclaimableBytes
        )})? This action cannot be undone.`
      )
    ) {
      return;
    }

    try {
      setCleaningStorage(true);
      setMessage('');

      const response = await api.post('/notion-sync/storage-cleanup', { user_id: actorId });
      setMessage(response.data?.message || 'Storage cleanup completed.');
      setStorageAudit(null);
    } catch (error) {
      console.error('Notion storage cleanup error:', error);
      setMessage(error.response?.data?.message || 'Failed to run storage cleanup.');
    } finally {
      setCleaningStorage(false);
    }
  };

  const latestJob = jobs[0] || null;
  const connectionStatus = config?.connectionStatus || (config?.connected ? 'connected' : 'disconnected');
  const needsReconnect = connectionStatus === 'reconnect_required';
  const connectionLabel = needsReconnect
    ? 'Reconnect required'
    : config?.connected
    ? 'Connected'
    : 'Not connected';

  return (
    <div className="ns-page">
      <PageHeader
        title="Notion Sync"
        subtitle="Connect Notion and review updates before publishing them."
      />

      {message ? <div className="ns-feedback">{message}</div> : null}

      <section className="ns-summary-grid">
        <div className="ns-summary-card status">
          <span>Connection</span>
          <strong>{connectionLabel}</strong>
        </div>

        <div className="ns-summary-card pending">
          <span>Pending Review</span>
          <strong>{pending.length}</strong>
        </div>

        <div className="ns-summary-card">
          <span>Sync Jobs</span>
          <strong>{jobs.length}</strong>
        </div>

        <div className="ns-summary-card">
          <span>Last Check</span>
          <strong>{latestJob?.completed_at || latestJob?.started_at || '-'}</strong>
        </div>
      </section>

      <section className="ns-card ns-app-card">
        <div className="ns-section-head">
          <div>
            <span className="ns-kicker">Integration</span>
            <h2>Notion App</h2>
          </div>

          <span className={`ns-status-pill ${appConfig?.configured ? 'connected' : 'idle'}`}>
            <i />
            {!appConfig?.configured
              ? 'Not configured'
              : appConfig.source === 'database'
              ? 'Custom app'
              : 'Server default'}
          </span>
        </div>

        <p className="ns-section-copy">
          Point this Knowledge Base at a specific Notion integration -- use this
          if a different client wants their own app (their own name/logo on
          the Notion sign-in screen) instead of the shared default. Switching
          which Notion <em>workspace</em> is connected does not need this --
          just Disconnect and Connect Notion again below.
        </p>

        {appConfigMessage ? <div className="ns-feedback">{appConfigMessage}</div> : null}

        {appConfig?.configured ? (
          <div className="ns-source-info">
            <div>
              <span>Client ID</span>
              <strong>{appConfig.clientId || '-'}</strong>
            </div>
            <div>
              <span>Client Secret</span>
              <strong>
                {appConfig.source === 'database'
                  ? appConfig.clientSecretHint || '-'
                  : 'Set on server'}
              </strong>
            </div>
            <div>
              <span>Source</span>
              <strong>{appConfig.source === 'database' ? 'Saved here' : 'Server default'}</strong>
            </div>
          </div>
        ) : null}

        <form className="ns-form" onSubmit={handleSaveAppConfig}>
          <label className="ns-field">
            <span>Client ID</span>
            <input
              type="text"
              name="clientId"
              value={appForm.clientId}
              onChange={handleAppFormChange}
              placeholder="Paste the integration's Client ID"
              autoComplete="off"
            />
          </label>

          <label className="ns-field">
            <span>Client Secret</span>
            <input
              type="password"
              name="clientSecret"
              value={appForm.clientSecret}
              onChange={handleAppFormChange}
              placeholder="Paste the integration's Client Secret"
              autoComplete="off"
            />
          </label>

          <div className="ns-actions">
            {appConfig?.source === 'database' ? (
              <button
                type="button"
                className="ns-btn secondary"
                onClick={handleResetAppConfig}
                disabled={resettingAppConfig || savingAppConfig}
              >
                {resettingAppConfig ? 'Resetting...' : 'Reset to server default'}
              </button>
            ) : null}
            <button type="submit" className="ns-btn primary" disabled={savingAppConfig}>
              {savingAppConfig ? 'Saving...' : 'Save Notion App'}
            </button>
          </div>
        </form>
      </section>

      <div className="ns-layout">
        <section className="ns-card ns-source-card">
          <div className="ns-section-head">
            <div>
              <span className="ns-kicker">Workspace</span>
              <h2>Notion Connection</h2>
            </div>

            <span className={`ns-status-pill ${needsReconnect ? 'warning' : config?.connected ? 'connected' : 'idle'}`}>
              <i />
              {connectionLabel}
            </span>
          </div>

          {loading ? (
            <div className="ns-loading">Loading connection...</div>
          ) : needsReconnect ? (
            <>
              <p className="ns-section-copy">
                Your Notion authorization is no longer valid. Please reconnect your workspace.
              </p>

              <div className="ns-source-info">
                <div>
                  <span>Workspace</span>
                  <strong>{config.workspaceName || 'Notion workspace'}</strong>
                </div>

                <div>
                  <span>Last Sync</span>
                  <strong>{config.lastSyncAt || '-'}</strong>
                </div>

                {config.lastError ? (
                  <div>
                    <span>Last Error</span>
                    <strong>{config.lastError}</strong>
                  </div>
                ) : null}
              </div>

              <div className="ns-connection-actions">
                <button
                  type="button"
                  className="ns-btn primary"
                  onClick={handleConnect}
                  disabled={connecting || !appConfig?.configured}
                >
                  {connecting ? 'Opening Notion...' : 'Reconnect Notion'}
                </button>
                <button
                  type="button"
                  className="ns-btn secondary"
                  onClick={handleDisconnect}
                  disabled={disconnecting}
                >
                  {disconnecting ? 'Disconnecting...' : 'Disconnect'}
                </button>
              </div>
            </>
          ) : config?.connected ? (
            <>
              <p className="ns-section-copy">
                Notion is connected. You do not need to remain logged in to Notion for future syncs.
              </p>

              <div className="ns-source-info">
                <div>
                  <span>Workspace</span>
                  <strong>{config.workspaceName || 'Notion workspace'}</strong>
                </div>

                <div>
                  <span>Connected</span>
                  <strong>{config.updatedAt || '-'}</strong>
                </div>

                <div>
                  <span>Last Sync</span>
                  <strong>{config.lastSyncAt || 'Never'}</strong>
                </div>
              </div>

              <div className="ns-connection-actions">
                <button
                  type="button"
                  className="ns-btn secondary"
                  onClick={handleDisconnect}
                  disabled={disconnecting}
                >
                  {disconnecting ? 'Disconnecting...' : 'Disconnect'}
                </button>
              </div>
            </>
          ) : (
            <div className="ns-connect-empty">
              <div className="ns-notion-icon">N</div>
              <div>
                <strong>No workspace connected</strong>
                <p>
                  Connect and authorize your Notion workspace once. After
                  connection, future syncs do not require you to stay logged
                  in to Notion.
                </p>
              </div>

              <button
                type="button"
                className="ns-btn primary"
                onClick={handleConnect}
                disabled={connecting || !appConfig?.configured}
              >
                {connecting ? 'Opening Notion...' : 'Connect Notion'}
              </button>

              {!appConfig?.configured ? (
                <p className="ns-section-copy">
                  Add a Notion app's Client ID and Client Secret above first.
                </p>
              ) : null}
            </div>
          )}
        </section>

        <section className="ns-card ns-sync-card">
          <div className="ns-sync-hero">
            <div className="ns-notion-icon">N</div>
            <div>
              <span className="ns-kicker">Knowledge Sync</span>
              <h2>Check for Updates</h2>
              <p>Finds new and edited Notion pages and queues them below for review -- nothing is published automatically.</p>
            </div>
          </div>

          <button
            className="ns-sync-btn"
            type="button"
            disabled={checking || !config?.connected}
            onClick={() => handleCheckForUpdates()}
          >
            {checking ? 'Checking Notion...' : 'Check for Updates'}
          </button>

          {needsReconnect ? (
            <div className="ns-sync-note">
              <span>Reconnect Notion above to resume syncing.</span>
            </div>
          ) : null}

          {checkResult ? (
            <div className="ns-sync-result-grid">
              <div>
                <span>New</span>
                <strong>{checkResult.new ?? 0}</strong>
              </div>
              <div>
                <span>Flagged</span>
                <strong>{checkResult.flagged ?? 0}</strong>
              </div>
              <div>
                <span>Unchanged</span>
                <strong>{checkResult.unchanged ?? 0}</strong>
              </div>
              <div className={Number(checkResult.failed) > 0 ? 'failed' : ''}>
                <span>Failed</span>
                <strong>{checkResult.failed ?? 0}</strong>
              </div>
              {Number(checkResult.inaccessible) > 0 ? (
                <div className="failed">
                  <span>Inaccessible</span>
                  <strong>{checkResult.inaccessible}</strong>
                </div>
              ) : null}
            </div>
          ) : (
            <div className="ns-sync-note">
              <span>Safe to run again — unchanged pages are skipped.</span>
            </div>
          )}

          {checkResult?.inaccessible > 0 ? (
            <div className="ns-sync-note">
              <span>
                Some Notion pages are no longer accessible. They may have
                been removed from the integration's permissions.
              </span>
            </div>
          ) : null}
        </section>
      </div>

      <section className="ns-card ns-pending-section">
        <div className="ns-section-head">
          <div>
            <span className="ns-kicker">Review Queue</span>
            <h2>Pending Updates</h2>
          </div>
        </div>

        <div className="ns-review-tabs">
          <button
            type="button"
            className={activeTab === 'pending' ? 'active' : ''}
            onClick={() => switchTab('pending')}
          >
            Pending
            <span>{pending.length}</span>
          </button>
          <button
            type="button"
            className={activeTab === 'trash' ? 'active' : ''}
            onClick={() => switchTab('trash')}
          >
            Trash
            <span>{trashed.length}</span>
          </button>
          <button
            type="button"
            className={activeTab === 'obsolete' ? 'active' : ''}
            onClick={() => switchTab('obsolete')}
          >
            Obsolete
            <span>{obsolete.length}</span>
          </button>
        </div>

        <p className="ns-section-copy">
          {activeTab === 'pending'
            ? 'Every new or changed Notion page waits here first -- nothing reaches the Knowledge Base until you approve it below.'
            : activeTab === 'trash'
            ? 'Items here are held temporarily. Restore them back to Pending, or delete them permanently to free up storage.'
            : 'Pages permanently deleted from the Knowledge Base. Their stored content and images are gone, but this record keeps future syncs from showing them again as new.'}
        </p>

        {activeTab === 'obsolete' ? (
          obsolete.length === 0 ? (
            <div className="ns-empty small">
              <strong>Nothing Obsolete</strong>
              <span>Pages you permanently delete from Trash will appear here.</span>
            </div>
          ) : (
            <div className="ns-pending-list">
              {obsolete.map((item) => {
                const isExpanded = expandedObsoleteId === item.id;
                const isRestoring = restoringObsoleteId === item.id;
                const isMissing = item.obsolete_status === 'missing';
                const isUpdated = item.obsolete_status === 'updated';

                return (
                  <article className="ns-pending-card" key={item.id}>
                    <div className="ns-pending-head">
                      <div className="ns-pending-info">
                        <h3>{item.page_title || 'Untitled'}</h3>
                        <p>
                          {isMissing
                            ? 'Status: Missing from Notion'
                            : `Deleted: ${item.deleted_at || '-'}`}
                          {!isMissing && item.latest_notion_edited_time
                            ? ` · Notion modified: ${item.latest_notion_edited_time}`
                            : ''}
                        </p>
                      </div>
                      <span className={`ns-review-pill ${isUpdated ? 'updated' : ''}`}>
                        {isMissing ? 'Missing' : isUpdated ? 'Updated in Notion' : 'Obsolete'}
                      </span>
                    </div>

                    {isMissing ? (
                      <p className="ns-section-copy">
                        The source Notion page may have been deleted, archived, or permission may have been removed.
                      </p>
                    ) : null}

                    <div className="ns-pending-actions">
                      <button
                        type="button"
                        className="ns-btn secondary"
                        onClick={() => setExpandedObsoleteId(isExpanded ? null : item.id)}
                      >
                        {isExpanded ? 'Hide Details' : 'View Details'}
                      </button>
                      <button
                        type="button"
                        className="ns-btn primary"
                        disabled={isRestoring}
                        onClick={() => handleRestoreObsolete(item.id)}
                      >
                        {isRestoring
                          ? 'Working...'
                          : isUpdated ? 'Restore Latest Version' : 'Restore'}
                      </button>
                    </div>

                    {isExpanded && (
                      <div className="ns-source-info">
                        <div>
                          <span>Notion Page ID</span>
                          <strong>{item.notion_page_id}</strong>
                        </div>
                        <div>
                          <span>Deleted At</span>
                          <strong>{item.deleted_at || '-'}</strong>
                        </div>
                        <div>
                          <span>Last Known Edit (before deletion)</span>
                          <strong>{item.last_known_notion_edited_time || '-'}</strong>
                        </div>
                        <div>
                          <span>Latest Notion Edit</span>
                          <strong>{item.latest_notion_edited_time || '-'}</strong>
                        </div>
                        <div>
                          <span>Status</span>
                          <strong>{item.obsolete_status}</strong>
                        </div>
                        <div>
                          <span>Last Checked</span>
                          <strong>{item.last_checked_at || '-'}</strong>
                        </div>
                        <div>
                          <span>Updated After Deletion</span>
                          <strong>{item.updated_after_obsolete ? 'Yes' : 'No'}</strong>
                        </div>
                      </div>
                    )}
                  </article>
                );
              })}
            </div>
          )
        ) : (
          <>
        {activeList.length > 0 ? (
          <div className="ns-bulk-toolbar" role="toolbar" aria-label="Bulk actions">
            <label className="ns-select-all">
              <input
                type="checkbox"
                checked={activeList.length > 0 && activeList.every((item) => selectedIds.includes(item.id))}
                onChange={toggleSelectAllVisible}
              />
              Select All
            </label>

            {selectedIds.filter((id) => activeList.some((item) => item.id === id)).length > 0 ? (
              <>
                <span className="ns-selection-count">
                  {selectedIds.filter((id) => activeList.some((item) => item.id === id)).length} selected
                </span>

                {activeTab === 'pending' ? (
                  <button
                    type="button"
                    className="ns-btn secondary"
                    onClick={bulkTrashSelected}
                    disabled={bulkProcessing}
                  >
                    {bulkProcessing ? 'Working...' : 'Move to Trash'}
                  </button>
                ) : (
                  <>
                    <button
                      type="button"
                      className="ns-btn secondary"
                      onClick={bulkRestoreSelected}
                      disabled={bulkProcessing}
                    >
                      {bulkProcessing ? 'Working...' : 'Restore Selected'}
                    </button>
                    <button
                      type="button"
                      className="ns-btn danger"
                      onClick={bulkPermanentDeleteSelected}
                      disabled={bulkProcessing}
                    >
                      {bulkProcessing ? 'Working...' : 'Delete Permanently'}
                    </button>
                  </>
                )}
              </>
            ) : null}
          </div>
        ) : null}

        {activeList.length === 0 ? (
          <div className="ns-empty small">
            <strong>{activeTab === 'pending' ? 'No pending updates' : 'Trash is empty'}</strong>
            <span>
              {activeTab === 'pending'
                ? 'Your published articles are up to date.'
                : 'Items moved to Trash will appear here.'}
            </span>
          </div>
        ) : (
          <div className="ns-pending-list">
            {activeList.map((item) => {
              const isExpanded = expandedPendingId === item.id;
              const isResolving = resolvingId === item.id || singleActionId === item.id;
              const isNew = item.article_id === null || item.article_id === undefined;
              const isSelected = selectedIds.includes(item.id);

              return (
                <article className={`ns-pending-card ${isSelected ? 'selected' : ''}`} key={item.id}>
                  <div className="ns-pending-head">
                    <label className="ns-pending-select">
                      <input
                        type="checkbox"
                        checked={isSelected}
                        onChange={() => toggleSelection(item.id)}
                        aria-label={`Select ${item.proposed_title || item.previous_title}`}
                      />
                    </label>

                    <div className="ns-pending-info">
                      <h3>{item.proposed_title || item.previous_title}</h3>
                      <p>
                        {activeTab === 'trash'
                          ? 'Moved to Trash'
                          : isNew ? 'Found in Notion' : 'Changed in Notion'}
                        {': '}
                        {(activeTab === 'trash' ? item.trashed_at : item.notion_last_edited_time) || '-'}
                      </p>
                    </div>
                    <span className="ns-review-pill">
                      {activeTab === 'trash' ? 'Trashed' : (isNew ? 'New' : 'Review')}
                    </span>
                  </div>

                  <div className="ns-pending-actions">
                    <button
                      type="button"
                      className="ns-btn secondary"
                      onClick={() => setExpandedPendingId(isExpanded ? null : item.id)}
                    >
                      {isExpanded ? 'Hide Preview' : (isNew ? 'Preview' : 'Review Changes')}
                    </button>

                    {activeTab === 'pending' ? (
                      <>
                        <button
                          type="button"
                          className="ns-btn secondary"
                          disabled={isResolving}
                          onClick={() => handleTrashItem(item.id)}
                        >
                          {isResolving ? 'Working...' : 'Move to Trash'}
                        </button>
                        <button
                          type="button"
                          className="ns-btn primary"
                          disabled={isResolving}
                          onClick={() => handleResolvePending(item.id, 'apply')}
                        >
                          {isResolving
                            ? 'Working...'
                            : (isNew ? 'Add to Knowledge Base' : 'Update to Latest')}
                        </button>
                      </>
                    ) : (
                      <>
                        <button
                          type="button"
                          className="ns-btn secondary"
                          disabled={isResolving}
                          onClick={() => handleRestoreItem(item.id)}
                        >
                          {isResolving ? 'Working...' : 'Restore'}
                        </button>
                        <button
                          type="button"
                          className="ns-btn danger"
                          disabled={isResolving}
                          onClick={() => handlePermanentDeleteItem(item.id)}
                        >
                          {isResolving ? 'Working...' : 'Delete Permanently'}
                        </button>
                      </>
                    )}
                  </div>

                  {isExpanded && (
                    <div className="ns-compare-grid">
                      <div className="ns-version-card current">
                        <div className="ns-version-label">Current</div>
                        {isNew ? (
                          <p className="ns-section-copy">Not yet in your Knowledge Base.</p>
                        ) : (
                          <div
                            className="article-rich-content"
                            dangerouslySetInnerHTML={{ __html: item.previous_content || '' }}
                          />
                        )}
                      </div>

                      <div className="ns-version-card proposed">
                        <div className="ns-version-label">From Notion</div>
                        <div
                          className="article-rich-content"
                          dangerouslySetInnerHTML={{ __html: item.proposed_content || '' }}
                        />
                      </div>
                    </div>
                  )}
                </article>
              );
            })}
          </div>
        )}
          </>
        )}
      </section>

      <section className="ns-card ns-storage-card">
        <div className="ns-section-head">
          <div>
            <span className="ns-kicker">Maintenance</span>
            <h2>Storage Cleanup</h2>
          </div>
        </div>

        <p className="ns-section-copy">
          Scans for image/file uploads on the server that no article or pending
          Notion item references any more. Nothing is deleted until you confirm.
        </p>

        <div className="ns-actions">
          <button
            type="button"
            className="ns-btn secondary"
            onClick={handleRunStorageAudit}
            disabled={runningAudit}
          >
            {runningAudit ? 'Scanning...' : 'Run Storage Audit'}
          </button>

          {storageAudit && storageAudit.orphanFileCount > 0 ? (
            <button
              type="button"
              className="ns-btn danger"
              onClick={handleCleanStorage}
              disabled={cleaningStorage}
            >
              {cleaningStorage ? 'Cleaning...' : 'Clean Unused Files'}
            </button>
          ) : null}
        </div>

        {storageAudit ? (
          <div className="ns-sync-result-grid">
            <div>
              <span>Upload files</span>
              <strong>{storageAudit.totalFiles}</strong>
            </div>
            <div>
              <span>Used by articles</span>
              <strong>{storageAudit.referencedByArticles}</strong>
            </div>
            <div>
              <span>Used by pending items</span>
              <strong>{storageAudit.referencedByPendingUpdates}</strong>
            </div>
            <div className={storageAudit.orphanFileCount > 0 ? 'failed' : ''}>
              <span>Potential orphans</span>
              <strong>{storageAudit.orphanFileCount}</strong>
            </div>
          </div>
        ) : null}

        {storageAudit && storageAudit.orphanFileCount > 0 ? (
          <div className="ns-sync-note">
            <span>
              Estimated reclaimable space: {formatBytes(storageAudit.estimatedReclaimableBytes)}
            </span>
          </div>
        ) : null}
      </section>

      <section className="ns-card ns-history">
        <div className="ns-section-head">
          <div>
            <span className="ns-kicker">History</span>
            <h2>Sync History</h2>
          </div>
          <span className="ns-count">{jobs.length}</span>
        </div>

        {jobs.length === 0 ? (
          <div className="ns-empty small">
            <strong>No sync history</strong>
            <span>Run your first Notion update check.</span>
          </div>
        ) : (
          <div className="ns-table-wrap">
            <table className="ns-table">
              <thead>
                <tr>
                  <th>Date</th>
                  <th>Status</th>
                  <th>New</th>
                  <th>Flagged</th>
                  <th>Unchanged</th>
                  <th>Failed</th>
                </tr>
              </thead>
              <tbody>
                {jobs.map((job) => (
                  <tr key={job.id}>
                    <td>{job.completed_at || job.started_at || '-'}</td>
                    <td>
                      <span className={`ns-job-status ${job.status || 'unknown'}`}>
                        {job.status}
                      </span>
                    </td>
                    <td>{job.imported_count ?? 0}</td>
                    <td>{job.updated_count ?? 0}</td>
                    <td>{job.skipped_count ?? 0}</td>
                    <td>{job.failed_count ?? 0}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  );
}
