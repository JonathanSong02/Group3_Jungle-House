import { useEffect, useRef, useState } from 'react';
import PageHeader from '../../components/PageHeader';
import api from '../../services/api';
import { useAuth } from '../../context/AuthContext';
import { useLanguage } from '../../i18n/LanguageContext';
import { translateServerMessage } from '../../i18n/serverMessages';
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
  const { t, tOr } = useLanguage();
  // Backend replies are English; translate the known ones before showing them.
  const tm = (text) => translateServerMessage(t, text);
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

    if (connected) return t('ns.connectedOk');
    if (error) return t('ns.connectFailed', { detail: error.replace(/_/g, ' ') });
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
      setMessage(t('ns.err.loadStatus'));
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
      setAppConfigMessage(t('ns.err.bothRequired'));
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

      setAppConfigMessage(t('ns.ok.appSaved'));
      setAppConfig(response.data?.appConfig || null);
      // Never keep the raw secret sitting in state longer than needed.
      setAppForm((prev) => ({ ...prev, clientSecret: '' }));
    } catch (error) {
      console.error('Save Notion app config error:', error);
      setAppConfigMessage(
        tm(error.response?.data?.message) || t('ns.err.appSave')
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

      setAppConfigMessage(t('ns.ok.appReset'));
      setAppConfig(response.data?.appConfig || null);
      setAppForm({ clientId: response.data?.appConfig?.clientId || '', clientSecret: '' });
    } catch (error) {
      console.error('Reset Notion app config error:', error);
      setAppConfigMessage(
        tm(error.response?.data?.message) || t('ns.err.appReset')
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
      if (!silent) setMessage(tm(response.data?.message) || '');
      await Promise.all([fetchJobs(), fetchPending(), fetchObsolete()]);
    } catch (error) {
      console.error('Check Notion for updates error:', error);
      if (!silent) {
        setMessage(
          tm(error.response?.data?.message) || t('ns.err.check')
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
      setMessage(t('ns.connectedOk'));
      handleCheckForUpdates({ silent: true });
    } else if (error) {
      setMessage(t('ns.connectFailed', { detail: error.replace(/_/g, ' ') }));
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
        finishConnectAttempt(t('ns.connectedOk'), { connected: true });
      } else {
        const detail = event.data.detail || 'connection_failed';
        finishConnectAttempt(t('ns.connectFailed', { detail: detail.replace(/_/g, ' ') }));
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
        throw new Error(t('ns.err.noAuthUrl'));
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
        tm(error.response?.data?.message) || t('ns.err.start')
      );
      setConnecting(false);
    }
  };

  const handleDisconnect = async () => {
    if (
      !window.confirm(
        t('ns.confirm.disconnect')
      )
    ) {
      return;
    }

    try {
      setDisconnecting(true);
      setMessage('');

      await api.post('/notion-sync/disconnect', {
        user_id: actorId,
      });

      setMessage(t('ns.ok.disconnected'));
      setConfig(null);
      setCheckResult(null);
      setPending([]);
    } catch (error) {
      console.error('Disconnect Notion error:', error);
      setMessage(
        tm(error.response?.data?.message) || t('ns.err.disconnect')
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

      setMessage(tm(response.data?.message) || t('ns.done'));
      setPending((prev) => prev.filter((item) => item.id !== pendingId));

      if (expandedPendingId === pendingId) {
        setExpandedPendingId(null);
      }

      await fetchJobs();
    } catch (error) {
      console.error(`Resolve Notion pending update (${action}) error:`, error);
      setMessage(
        tm(error.response?.data?.message) ||
          t('ns.err.resolve')
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

      await api.post(`/notion-sync/pending-updates/${pendingId}/trash`, {
        user_id: actorId,
      });

      setMessage(t('ns.ok.trashed'));
      setPending((prev) => prev.filter((item) => item.id !== pendingId));
      setSelectedIds((prev) => prev.filter((id) => id !== pendingId));
      fetchTrashed();
    } catch (error) {
      console.error('Trash Notion pending update error:', error);
      setMessage(tm(error.response?.data?.message) || t('ns.err.trash'));
    } finally {
      setSingleActionId(null);
    }
  };

  const handleRestoreItem = async (pendingId) => {
    try {
      setSingleActionId(pendingId);
      setMessage('');

      await api.post(`/notion-sync/pending-updates/${pendingId}/restore`, {
        user_id: actorId,
      });

      setMessage(t('ns.ok.restored'));
      setTrashed((prev) => prev.filter((item) => item.id !== pendingId));
      setSelectedIds((prev) => prev.filter((id) => id !== pendingId));
      fetchPending();
    } catch (error) {
      console.error('Restore Notion pending update error:', error);
      setMessage(tm(error.response?.data?.message) || t('ns.err.restore'));
    } finally {
      setSingleActionId(null);
    }
  };

  const handlePermanentDeleteItem = async (pendingId) => {
    const item = trashed.find((t) => t.id === pendingId);
    const isNewPage = !item || item.article_id === null || item.article_id === undefined;

    const confirmText = isNewPage ? t('ns.confirm.permNew') : t('ns.confirm.permEdit');

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
      setMessage(`${t('ns.ok.permDeleted')} ${t('ns.ok.filesRemoved', { n: deletedFiles })}`);
      setTrashed((prev) => prev.filter((item) => item.id !== pendingId));
      setSelectedIds((prev) => prev.filter((id) => id !== pendingId));
      if (response.data?.obsoleteCreated) {
        fetchObsolete();
      }
    } catch (error) {
      console.error('Permanent delete Notion pending update error:', error);
      setMessage(tm(error.response?.data?.message) || t('ns.err.permDelete'));
    } finally {
      setSingleActionId(null);
    }
  };

  const handleRestoreObsolete = async (obsoleteId) => {
    try {
      setRestoringObsoleteId(obsoleteId);
      setMessage('');

      await api.post(`/notion-sync/obsolete/${obsoleteId}/restore`, {
        user_id: actorId,
      });

      setMessage(t('ns.ok.obsoleteRestored'));
      setObsolete((prev) => prev.filter((item) => item.id !== obsoleteId));
      if (expandedObsoleteId === obsoleteId) setExpandedObsoleteId(null);
      await fetchPending();
    } catch (error) {
      console.error('Restore Notion obsolete article error:', error);
      setMessage(tm(error.response?.data?.message) || t('ns.err.restoreArticle'));
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

      await api.post(endpoint, { ids: idsToUse, user_id: actorId });

      setMessage(successFallback(idsToUse.length));
      setSelectedIds([]);
      await Promise.all([fetchPending(), fetchTrashed()]);
    } catch (error) {
      console.error(`Bulk action error (${endpoint}):`, error);
      setMessage(tm(error.response?.data?.message) || errorFallback);
    } finally {
      setBulkProcessing(false);
    }
  };

  const bulkApplySelected = () =>
    runBulkAction({
      endpoint: '/notion-sync/pending-updates/bulk-apply',
      confirmText: null,
      successFallback: (count) => t('ns.bulk.okApply', { n: count }),
      errorFallback: t('ns.bulk.errApply'),
    });

  const bulkTrashSelected = () =>
    runBulkAction({
      endpoint: '/notion-sync/pending-updates/bulk-trash',
      confirmText: (count) => t('ns.bulk.confirmTrash', { n: count }),
      successFallback: (count) => t('ns.bulk.okTrash', { n: count }),
      errorFallback: t('ns.bulk.errTrash'),
    });

  const bulkRestoreSelected = () =>
    runBulkAction({
      endpoint: '/notion-sync/pending-updates/bulk-restore',
      confirmText: null,
      successFallback: (count) => t('ns.bulk.okRestore', { n: count }),
      errorFallback: t('ns.bulk.errRestore'),
    });

  const bulkPermanentDeleteSelected = async () => {
    const idsToUse = selectedIds.filter((id) => activeList.some((item) => item.id === id));
    if (idsToUse.length === 0) return;

    if (
      !window.confirm(t('ns.bulk.confirmPerm', { n: idsToUse.length }))
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
      setMessage(t('ns.bulk.okPerm', { n: deletedArticles, files: deletedFiles }));
      setSelectedIds([]);
      await Promise.all([fetchPending(), fetchTrashed()]);
      if (obsoleteCreated) {
        fetchObsolete();
      }
    } catch (error) {
      console.error('Bulk permanent delete error:', error);
      setMessage(tm(error.response?.data?.message) || t('ns.bulk.errPerm'));
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
      setMessage(tm(error.response?.data?.message) || t('ns.err.audit'));
    } finally {
      setRunningAudit(false);
    }
  };

  const handleCleanStorage = async () => {
    const orphanCount = storageAudit?.orphanFileCount || 0;
    if (orphanCount === 0) return;

    if (
      !window.confirm(
        t('ns.confirm.clean', {
          n: orphanCount,
          size: formatBytes(storageAudit?.estimatedReclaimableBytes),
        })
      )
    ) {
      return;
    }

    try {
      setCleaningStorage(true);
      setMessage('');

      await api.post('/notion-sync/storage-cleanup', { user_id: actorId });
      setMessage(t('ns.ok.cleaned'));
      setStorageAudit(null);
    } catch (error) {
      console.error('Notion storage cleanup error:', error);
      setMessage(tm(error.response?.data?.message) || t('ns.err.clean'));
    } finally {
      setCleaningStorage(false);
    }
  };

  const latestJob = jobs[0] || null;
  const connectionStatus = config?.connectionStatus || (config?.connected ? 'connected' : 'disconnected');
  const needsReconnect = connectionStatus === 'reconnect_required';
  const connectionLabel = needsReconnect
    ? t('ns.conn.reconnect')
    : config?.connected
    ? t('ns.conn.connected')
    : t('ns.conn.notConnected');

  return (
    <div className="ns-page">
      <PageHeader
        title={t('ns.title')}
        subtitle={t('ns.subtitle')}
      />

      {message ? <div className="ns-feedback">{message}</div> : null}

      <section className="ns-summary-grid">
        <div className="ns-summary-card status">
          <span>{t('ns.connection')}</span>
          <strong>{connectionLabel}</strong>
        </div>

        <div className="ns-summary-card pending">
          <span>{t('ns.pendingReview')}</span>
          <strong>{pending.length}</strong>
        </div>

        <div className="ns-summary-card">
          <span>{t('ns.syncJobs')}</span>
          <strong>{jobs.length}</strong>
        </div>

        <div className="ns-summary-card">
          <span>{t('ns.lastCheck')}</span>
          <strong>{latestJob?.completed_at || latestJob?.started_at || '-'}</strong>
        </div>
      </section>

      <section className="ns-card ns-app-card">
        <div className="ns-section-head">
          <div>
            <span className="ns-kicker">{t('ns.integration')}</span>
            <h2>{t('ns.app')}</h2>
          </div>

          <span className={`ns-status-pill ${appConfig?.configured ? 'connected' : 'idle'}`}>
            <i />
            {!appConfig?.configured
              ? t('ns.app.notConfigured')
              : appConfig.source === 'database'
              ? t('ns.app.custom')
              : t('ns.app.default')}
          </span>
        </div>

        <p className="ns-section-copy">{t('ns.app.copy')}</p>

        {appConfigMessage ? <div className="ns-feedback">{appConfigMessage}</div> : null}

        {appConfig?.configured ? (
          <div className="ns-source-info">
            <div>
              <span>{t('ns.clientId')}</span>
              <strong>{appConfig.clientId || '-'}</strong>
            </div>
            <div>
              <span>{t('ns.clientSecret')}</span>
              <strong>
                {appConfig.source === 'database'
                  ? appConfig.clientSecretHint || '-'
                  : t('ns.setOnServer')}
              </strong>
            </div>
            <div>
              <span>{t('ns.source')}</span>
              <strong>{appConfig.source === 'database' ? t('ns.savedHere') : t('ns.app.default')}</strong>
            </div>
          </div>
        ) : null}

        <form className="ns-form" onSubmit={handleSaveAppConfig}>
          <label className="ns-field">
            <span>{t('ns.clientId')}</span>
            <input
              type="text"
              name="clientId"
              value={appForm.clientId}
              onChange={handleAppFormChange}
              placeholder={t('ns.clientIdPh')}
              autoComplete="off"
            />
          </label>

          <label className="ns-field">
            <span>{t('ns.clientSecret')}</span>
            <input
              type="password"
              name="clientSecret"
              value={appForm.clientSecret}
              onChange={handleAppFormChange}
              placeholder={t('ns.clientSecretPh')}
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
                {resettingAppConfig ? t('ns.resetting') : t('ns.resetDefault')}
              </button>
            ) : null}
            <button type="submit" className="ns-btn primary" disabled={savingAppConfig}>
              {savingAppConfig ? t('ns.saving') : t('ns.saveApp')}
            </button>
          </div>
        </form>
      </section>

      <div className="ns-layout">
        <section className="ns-card ns-source-card">
          <div className="ns-section-head">
            <div>
              <span className="ns-kicker">{t('ns.workspace')}</span>
              <h2>{t('ns.notionConnection')}</h2>
            </div>

            <span className={`ns-status-pill ${needsReconnect ? 'warning' : config?.connected ? 'connected' : 'idle'}`}>
              <i />
              {connectionLabel}
            </span>
          </div>

          {loading ? (
            <div className="ns-loading">{t('ns.loadingConn')}</div>
          ) : needsReconnect ? (
            <>
              <p className="ns-section-copy">
                {t('ns.authInvalid')}
              </p>

              <div className="ns-source-info">
                <div>
                  <span>{t('ns.workspace')}</span>
                  <strong>{config.workspaceName || t('ns.notionWorkspace')}</strong>
                </div>

                <div>
                  <span>{t('ns.lastSync')}</span>
                  <strong>{config.lastSyncAt || '-'}</strong>
                </div>

                {config.lastError ? (
                  <div>
                    <span>{t('ns.lastError')}</span>
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
                  {connecting ? t('ns.opening') : t('ns.reconnectBtn')}
                </button>
                <button
                  type="button"
                  className="ns-btn secondary"
                  onClick={handleDisconnect}
                  disabled={disconnecting}
                >
                  {disconnecting ? t('ns.disconnecting') : t('ns.disconnect')}
                </button>
              </div>
            </>
          ) : config?.connected ? (
            <>
              <p className="ns-section-copy">
                {t('ns.connectedCopy')}
              </p>

              <div className="ns-source-info">
                <div>
                  <span>{t('ns.workspace')}</span>
                  <strong>{config.workspaceName || t('ns.notionWorkspace')}</strong>
                </div>

                <div>
                  <span>{t('ns.connectedAt')}</span>
                  <strong>{config.updatedAt || '-'}</strong>
                </div>

                <div>
                  <span>{t('ns.lastSync')}</span>
                  <strong>{config.lastSyncAt || t('ns.never')}</strong>
                </div>
              </div>

              <div className="ns-connection-actions">
                <button
                  type="button"
                  className="ns-btn secondary"
                  onClick={handleDisconnect}
                  disabled={disconnecting}
                >
                  {disconnecting ? t('ns.disconnecting') : t('ns.disconnect')}
                </button>
              </div>
            </>
          ) : (
            <div className="ns-connect-empty">
              <div className="ns-notion-icon">N</div>
              <div>
                <strong>{t('ns.noWorkspace')}</strong>
                <p>{t('ns.noWorkspaceCopy')}</p>
              </div>

              <button
                type="button"
                className="ns-btn primary"
                onClick={handleConnect}
                disabled={connecting || !appConfig?.configured}
              >
                {connecting ? t('ns.opening') : t('ns.connectBtn')}
              </button>

              {!appConfig?.configured ? (
                <p className="ns-section-copy">
                  {t('ns.addAppFirst')}
                </p>
              ) : null}
            </div>
          )}
        </section>

        <section className="ns-card ns-sync-card">
          <div className="ns-sync-hero">
            <div className="ns-notion-icon">N</div>
            <div>
              <span className="ns-kicker">{t('ns.knowledgeSync')}</span>
              <h2>{t('ns.checkUpdates')}</h2>
              <p>{t('ns.checkCopy')}</p>
            </div>
          </div>

          <button
            className="ns-sync-btn"
            type="button"
            disabled={checking || !config?.connected}
            onClick={() => handleCheckForUpdates()}
          >
            {checking ? t('ns.checking') : t('ns.checkUpdates')}
          </button>

          {needsReconnect ? (
            <div className="ns-sync-note">
              <span>{t('ns.reconnectNote')}</span>
            </div>
          ) : null}

          {checkResult ? (
            <div className="ns-sync-result-grid">
              <div>
                <span>{t('ns.result.new')}</span>
                <strong>{checkResult.new ?? 0}</strong>
              </div>
              <div>
                <span>{t('ns.result.flagged')}</span>
                <strong>{checkResult.flagged ?? 0}</strong>
              </div>
              <div>
                <span>{t('ns.result.unchanged')}</span>
                <strong>{checkResult.unchanged ?? 0}</strong>
              </div>
              <div className={Number(checkResult.failed) > 0 ? 'failed' : ''}>
                <span>{t('ns.result.failed')}</span>
                <strong>{checkResult.failed ?? 0}</strong>
              </div>
              {Number(checkResult.inaccessible) > 0 ? (
                <div className="failed">
                  <span>{t('ns.result.inaccessible')}</span>
                  <strong>{checkResult.inaccessible}</strong>
                </div>
              ) : null}
            </div>
          ) : (
            <div className="ns-sync-note">
              <span>{t('ns.safeRerun')}</span>
            </div>
          )}

          {checkResult?.inaccessible > 0 ? (
            <div className="ns-sync-note">
              <span>{t('ns.inaccessibleNote')}</span>
            </div>
          ) : null}
        </section>
      </div>

      <section className="ns-card ns-pending-section">
        <div className="ns-section-head">
          <div>
            <span className="ns-kicker">{t('ns.reviewQueue')}</span>
            <h2>{t('ns.pendingUpdates')}</h2>
          </div>
        </div>

        <div className="ns-review-tabs">
          <button
            type="button"
            className={activeTab === 'pending' ? 'active' : ''}
            onClick={() => switchTab('pending')}
          >
            {t('ns.tab.pending')}
            <span>{pending.length}</span>
          </button>
          <button
            type="button"
            className={activeTab === 'trash' ? 'active' : ''}
            onClick={() => switchTab('trash')}
          >
            {t('ns.tab.trash')}
            <span>{trashed.length}</span>
          </button>
          <button
            type="button"
            className={activeTab === 'obsolete' ? 'active' : ''}
            onClick={() => switchTab('obsolete')}
          >
            {t('ns.tab.obsolete')}
            <span>{obsolete.length}</span>
          </button>
        </div>

        <p className="ns-section-copy">
          {activeTab === 'pending'
            ? t('ns.copy.pending')
            : activeTab === 'trash'
            ? t('ns.copy.trash')
            : t('ns.copy.obsolete')}
        </p>

        {activeTab === 'obsolete' ? (
          obsolete.length === 0 ? (
            <div className="ns-empty small">
              <strong>{t('ns.nothingObsolete')}</strong>
              <span>{t('ns.nothingObsoleteHint')}</span>
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
                        <h3>{item.page_title || t('ns.untitled')}</h3>
                        <p>
                          {isMissing
                            ? t('ns.statusMissing')
                            : t('ns.deletedAt', { when: item.deleted_at || '-' })}
                          {!isMissing && item.latest_notion_edited_time
                            ? ` · ${t('ns.notionModified', { when: item.latest_notion_edited_time })}`
                            : ''}
                        </p>
                      </div>
                      <span className={`ns-review-pill ${isUpdated ? 'updated' : ''}`}>
                        {isMissing ? t('ns.pill.missing') : isUpdated ? t('ns.pill.updated') : t('ns.pill.obsolete')}
                      </span>
                    </div>

                    {isMissing ? (
                      <p className="ns-section-copy">
                        {t('ns.missingCopy')}
                      </p>
                    ) : null}

                    <div className="ns-pending-actions">
                      <button
                        type="button"
                        className="ns-btn secondary"
                        onClick={() => setExpandedObsoleteId(isExpanded ? null : item.id)}
                      >
                        {isExpanded ? t('ns.hideDetails') : t('ns.viewDetails')}
                      </button>
                      <button
                        type="button"
                        className="ns-btn primary"
                        disabled={isRestoring}
                        onClick={() => handleRestoreObsolete(item.id)}
                      >
                        {isRestoring
                          ? t('ns.working')
                          : isUpdated ? t('ns.restoreLatest') : t('ns.restore')}
                      </button>
                    </div>

                    {isExpanded && (
                      <div className="ns-source-info">
                        <div>
                          <span>{t('ns.d.pageId')}</span>
                          <strong>{item.notion_page_id}</strong>
                        </div>
                        <div>
                          <span>{t('ns.d.deletedAt')}</span>
                          <strong>{item.deleted_at || '-'}</strong>
                        </div>
                        <div>
                          <span>{t('ns.d.lastKnown')}</span>
                          <strong>{item.last_known_notion_edited_time || '-'}</strong>
                        </div>
                        <div>
                          <span>{t('ns.d.latest')}</span>
                          <strong>{item.latest_notion_edited_time || '-'}</strong>
                        </div>
                        <div>
                          <span>{t('ns.d.status')}</span>
                          <strong>{tOr(`ns.status.${item.obsolete_status}`, item.obsolete_status)}</strong>
                        </div>
                        <div>
                          <span>{t('ns.d.lastChecked')}</span>
                          <strong>{item.last_checked_at || '-'}</strong>
                        </div>
                        <div>
                          <span>{t('ns.d.updatedAfter')}</span>
                          <strong>{item.updated_after_obsolete ? t('ns.yes') : t('ns.no')}</strong>
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
          <div className="ns-bulk-toolbar" role="toolbar" aria-label={t('ns.bulkAria')}>
            <label className="ns-select-all">
              <input
                type="checkbox"
                checked={activeList.length > 0 && activeList.every((item) => selectedIds.includes(item.id))}
                onChange={toggleSelectAllVisible}
              />
              {t('ns.selectAll')}
            </label>

            {selectedIds.filter((id) => activeList.some((item) => item.id === id)).length > 0 ? (
              <>
                <span className="ns-selection-count">
                  {t('ns.nSelected', { n: selectedIds.filter((id) => activeList.some((item) => item.id === id)).length })}
                </span>

                {activeTab === 'pending' ? (
                  <>
                    <button
                      type="button"
                      className="ns-btn primary"
                      onClick={bulkApplySelected}
                      disabled={bulkProcessing}
                    >
                      {bulkProcessing ? t('ns.working') : t('ns.addToKb')}
                    </button>
                    <button
                      type="button"
                      className="ns-btn secondary"
                      onClick={bulkTrashSelected}
                      disabled={bulkProcessing}
                    >
                      {bulkProcessing ? t('ns.working') : t('ns.moveToTrash')}
                    </button>
                  </>
                ) : (
                  <>
                    <button
                      type="button"
                      className="ns-btn secondary"
                      onClick={bulkRestoreSelected}
                      disabled={bulkProcessing}
                    >
                      {bulkProcessing ? t('ns.working') : t('ns.restoreSelected')}
                    </button>
                    <button
                      type="button"
                      className="ns-btn danger"
                      onClick={bulkPermanentDeleteSelected}
                      disabled={bulkProcessing}
                    >
                      {bulkProcessing ? t('ns.working') : t('ns.deletePerm')}
                    </button>
                  </>
                )}
              </>
            ) : null}
          </div>
        ) : null}

        {activeList.length === 0 ? (
          <div className="ns-empty small">
            <strong>{activeTab === 'pending' ? t('ns.noPending') : t('ns.trashEmpty')}</strong>
            <span>
              {activeTab === 'pending'
                ? t('ns.upToDate')
                : t('ns.trashHint')}
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
                        aria-label={t('ns.selectItem', { title: item.proposed_title || item.previous_title })}
                      />
                    </label>

                    <div className="ns-pending-info">
                      <h3>{item.proposed_title || item.previous_title}</h3>
                      <p>
                        {activeTab === 'trash'
                          ? t('ns.movedToTrashLabel')
                          : isNew ? t('ns.foundInNotion') : t('ns.changedInNotion')}
                        {': '}
                        {(activeTab === 'trash' ? item.trashed_at : item.notion_last_edited_time) || '-'}
                      </p>
                    </div>
                    <span className="ns-review-pill">
                      {activeTab === 'trash' ? t('ns.pill.trashed') : (isNew ? t('ns.pill.new') : t('ns.pill.review'))}
                    </span>
                  </div>

                  <div className="ns-pending-actions">
                    <button
                      type="button"
                      className="ns-btn secondary"
                      onClick={() => setExpandedPendingId(isExpanded ? null : item.id)}
                    >
                      {isExpanded ? t('ns.hidePreview') : (isNew ? t('ns.preview') : t('ns.reviewChanges'))}
                    </button>

                    {activeTab === 'pending' ? (
                      <>
                        <button
                          type="button"
                          className="ns-btn secondary"
                          disabled={isResolving}
                          onClick={() => handleTrashItem(item.id)}
                        >
                          {isResolving ? t('ns.working') : t('ns.moveToTrash')}
                        </button>
                        <button
                          type="button"
                          className="ns-btn primary"
                          disabled={isResolving}
                          onClick={() => handleResolvePending(item.id, 'apply')}
                        >
                          {isResolving
                            ? t('ns.working')
                            : (isNew ? t('ns.addToKb') : t('ns.updateLatest'))}
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
                          {isResolving ? t('ns.working') : t('ns.restore')}
                        </button>
                        <button
                          type="button"
                          className="ns-btn danger"
                          disabled={isResolving}
                          onClick={() => handlePermanentDeleteItem(item.id)}
                        >
                          {isResolving ? t('ns.working') : t('ns.deletePerm')}
                        </button>
                      </>
                    )}
                  </div>

                  {isExpanded && (
                    <div className="ns-compare-grid">
                      <div className="ns-version-card current">
                        <div className="ns-version-label">{t('ns.current')}</div>
                        {isNew ? (
                          <p className="ns-section-copy">{t('ns.notYetInKb')}</p>
                        ) : (
                          <div
                            className="article-rich-content"
                            dangerouslySetInnerHTML={{ __html: item.previous_content || '' }}
                          />
                        )}
                      </div>

                      <div className="ns-version-card proposed">
                        <div className="ns-version-label">{t('ns.fromNotion')}</div>
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
            <span className="ns-kicker">{t('ns.maintenance')}</span>
            <h2>{t('ns.storageCleanup')}</h2>
          </div>
        </div>

        <p className="ns-section-copy">{t('ns.storageCopy')}</p>

        <div className="ns-actions">
          <button
            type="button"
            className="ns-btn secondary"
            onClick={handleRunStorageAudit}
            disabled={runningAudit}
          >
            {runningAudit ? t('ns.scanning') : t('ns.runAudit')}
          </button>

          {storageAudit && storageAudit.orphanFileCount > 0 ? (
            <button
              type="button"
              className="ns-btn danger"
              onClick={handleCleanStorage}
              disabled={cleaningStorage}
            >
              {cleaningStorage ? t('ns.cleaning') : t('ns.cleanBtn')}
            </button>
          ) : null}
        </div>

        {storageAudit ? (
          <div className="ns-sync-result-grid">
            <div>
              <span>{t('ns.audit.total')}</span>
              <strong>{storageAudit.totalFiles}</strong>
            </div>
            <div>
              <span>{t('ns.audit.articles')}</span>
              <strong>{storageAudit.referencedByArticles}</strong>
            </div>
            <div>
              <span>{t('ns.audit.pending')}</span>
              <strong>{storageAudit.referencedByPendingUpdates}</strong>
            </div>
            <div className={storageAudit.orphanFileCount > 0 ? 'failed' : ''}>
              <span>{t('ns.audit.orphans')}</span>
              <strong>{storageAudit.orphanFileCount}</strong>
            </div>
          </div>
        ) : null}

        {storageAudit && storageAudit.orphanFileCount > 0 ? (
          <div className="ns-sync-note">
            <span>
              {t('ns.audit.reclaim', { size: formatBytes(storageAudit.estimatedReclaimableBytes) })}
            </span>
          </div>
        ) : null}
      </section>

      <section className="ns-card ns-history">
        <div className="ns-section-head">
          <div>
            <span className="ns-kicker">{t('ns.history')}</span>
            <h2>{t('ns.syncHistory')}</h2>
          </div>
          <span className="ns-count">{jobs.length}</span>
        </div>

        {jobs.length === 0 ? (
          <div className="ns-empty small">
            <strong>{t('ns.noHistory')}</strong>
            <span>{t('ns.noHistoryHint')}</span>
          </div>
        ) : (
          <div className="ns-table-wrap">
            <table className="ns-table">
              <thead>
                <tr>
                  <th>{t('ns.col.date')}</th>
                  <th>{t('ns.col.status')}</th>
                  <th>{t('ns.col.new')}</th>
                  <th>{t('ns.col.flagged')}</th>
                  <th>{t('ns.col.unchanged')}</th>
                  <th>{t('ns.col.failed')}</th>
                </tr>
              </thead>
              <tbody>
                {jobs.map((job) => (
                  <tr key={job.id}>
                    <td>{job.completed_at || job.started_at || '-'}</td>
                    <td>
                      <span className={`ns-job-status ${job.status || 'unknown'}`}>
                        {tOr(`ns.job.${job.status}`, job.status)}
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
